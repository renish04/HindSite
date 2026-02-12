import os
import re
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from dotenv import load_dotenv
import cohere

from app.schemas import PageResult
from app.services.embeddings import embedder

load_dotenv()

# Stopwords so FTS uses OR over meaningful terms only (plainto_tsquery uses AND and matches nothing on long queries)
_FTS_STOP = frozenset(
    "a an and are as at be but by for if in into is it no not of on or such that the their then there these they this to was will with".split()
)


def _fts_query_or_tokens(query: str) -> str:
    """Build a tsquery string with OR semantics: 'word1 | word2 | word3'. Returns empty if no tokens."""
    words = re.findall(r"[a-zA-Z0-9]{3,}", query.lower())
    tokens = [w for w in words if w not in _FTS_STOP]
    if not tokens:
        return ""
    # Escape single quotes for PostgreSQL; join with |
    escaped = [t.replace("'", "''") for t in tokens]
    return " | ".join(escaped)


class SearchService:
    def __init__(self):
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            raise ValueError(
                "COHERE_API_KEY is not set. Add it to .env to use semantic search."
            )
        self.cohere_client = cohere.Client(api_key)

    def search_pages(self, query: str, db: Session, limit: int = 3) -> List[PageResult]:
        """
        Two-stage retrieval:
        1. Vector search with pgvector (retrieve top 20 candidates)
        2. Cross-encoder reranking with Cohere Rerank (return top 3)
        """
        print("[HindSite SEMANTIC] ========== Semantic search started ==========")
        print("[HindSite SEMANTIC] query=%r  limit=%d" % (query, limit))

        # Step 1: Query → vector (Cohere embed)
        try:
            query_embedding = embedder.generate_query_embedding(query)
        except Exception as e:
            raise RuntimeError(f"Embedding failed (check COHERE_API_KEY): {e}") from e
        candidate_limit = max(20, limit * 5)

        # Step 2a: Vector search (pgvector) - 70% weight
        print("[HindSite SEMANTIC] [vector] Running pgvector similarity search (candidate_limit=%d)" % candidate_limit)
        sql_vector = text("""
            SELECT id, url, title, domain, content, time_spent, scroll_percent, captured_at,
                   1 - (embedding <=> CAST(:embedding AS vector)) as similarity
            FROM captured_pages
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)
        result = db.execute(
            sql_vector,
            {"embedding": str(query_embedding), "limit": candidate_limit},
        )
        vector_rows = result.fetchall()

        # Step 2b: FTS with OR semantics (any query term matches) - 30% weight
        fts_query_or = _fts_query_or_tokens(query)
        print("[HindSite SEMANTIC] [fts] Running full-text search (ts_rank, OR terms) on title, domain, summary, content")
        print("[HindSite SEMANTIC] [fts] query=%r" % query)
        print("[HindSite SEMANTIC] [fts] fts_query_or=%r" % fts_query_or)
        fts_rows = []
        if fts_query_or:
            sql_fts = text("""
                SELECT id, ts_rank(
                    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(domain, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(summary, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(content, '')), 'B'),
                    to_tsquery('english', :fts_query)
                ) as fts_score
                FROM captured_pages
                WHERE (
                    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(domain, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(summary, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(content, '')), 'B')
                ) @@ to_tsquery('english', :fts_query)
                ORDER BY fts_score DESC
                LIMIT :limit
            """)
            try:
                fts_result = db.execute(sql_fts, {"fts_query": fts_query_or, "limit": candidate_limit})
                fts_rows = fts_result.fetchall()
                print("[HindSite SEMANTIC] [fts] FTS returned %d rows" % len(fts_rows))
                for i, r in enumerate(fts_rows):
                    rid = getattr(r, "id", None)
                    rscore = getattr(r, "fts_score", 0) or 0
                    print("[HindSite SEMANTIC] [fts]   [%d] id=%s fts_score=%.6f" % (i, rid, rscore))
            except Exception as e:
                print("[HindSite SEMANTIC] [fts] FTS failed (e.g. missing summary column): %s" % e)
                import traceback
                traceback.print_exc()
                fts_rows = []
        else:
            print("[HindSite SEMANTIC] [fts] No FTS tokens (query too short or only stopwords), skipping FTS")
        # Normalize id to string so lookup matches vector row id (uuid vs str)
        id_to_fts = {}
        for r in fts_rows:
            rid = getattr(r, "id", None)
            if rid is not None:
                id_to_fts[str(rid)] = getattr(r, "fts_score", 0) or 0
        max_fts = max(id_to_fts.values()) if id_to_fts else 1.0
        print("[HindSite SEMANTIC] [fts] id_to_fts size=%d max_fts=%.6f" % (len(id_to_fts), max_fts))

        # Merge: 70% vector + 30% FTS
        rows_with_score = []
        for row in vector_rows:
            vid = getattr(row, "id", None)
            vid_str = str(vid) if vid is not None else None
            v_score = getattr(row, "similarity", 0) or 0
            f_score = id_to_fts.get(vid_str, 0) / max_fts if max_fts > 0 else 0
            combined = 0.7 * v_score + 0.3 * f_score
            rows_with_score.append((row, combined))
        rows_with_score.sort(key=lambda x: -x[1])
        candidates = [r[0] for r in rows_with_score[:candidate_limit]]

        print("[HindSite SEMANTIC] [vector] Candidates after hybrid (70%% vector + 30%% FTS): %d" % len(candidates))
        for i, row in enumerate(candidates):
            v_score = getattr(row, "similarity", 0) or 0
            rid_str = str(getattr(row, "id", None)) if getattr(row, "id", None) is not None else None
            f_score = id_to_fts.get(rid_str, 0) / max_fts if max_fts > 0 else 0
            comb = 0.7 * v_score + 0.3 * f_score
            print("[HindSite SEMANTIC]   [%d] id=%s url=%s vector=%.4f fts=%.4f combined=%.4f" % (i, getattr(row, "id", ""), (getattr(row, "url", "") or "")[:50], v_score, f_score, comb))

        if not candidates:
            print("[HindSite SEMANTIC] No candidates → returning []")
            print("[HindSite SEMANTIC] ========== Semantic search finished ==========")
            return []

        documents = [row.content[:2000] if row.content else "" for row in candidates]
        print("[HindSite SEMANTIC] [rerank] Calling Cohere rerank (model=rerank-english-v3.0, top_n=%d, docs=%d)" % (limit, len(documents)))

        try:
            rerank_response = self.cohere_client.rerank(
                model="rerank-english-v3.0",
                query=query,
                documents=documents,
                top_n=limit,
                return_documents=False,
            )

            print("[HindSite SEMANTIC] [rerank] Rerank raw results:")
            for r in rerank_response.results:
                print("[HindSite SEMANTIC]   index=%d relevance_score=%.4f" % (r.index, r.relevance_score))

            results = []
            for rerank_result in rerank_response.results:
                # Only accept scores above 0 (exclude 0.0000; use min threshold so display-zero is out)
                if rerank_result.relevance_score <= 0.0001:
                    continue

                candidate = candidates[rerank_result.index]
                results.append(
                    PageResult(
                        id=candidate.id,
                        url=candidate.url,
                        title=candidate.title or self._extract_title(candidate.url),
                        domain=candidate.domain or self._extract_title(candidate.url) or "",
                        snippet=self._extract_snippet(candidate.content or "", query),
                        similarity=round(rerank_result.relevance_score, 3),
                        time_spent=candidate.time_spent,
                        captured_at=candidate.captured_at,
                    )
                )

            print("[HindSite SEMANTIC] After filter (score > 0.0001): %d results" % len(results))
            print("[HindSite SEMANTIC] ========== Semantic search finished ==========")
            return results

        except Exception as e:
            print("[HindSite SEMANTIC] Reranking failed: %s → falling back to vector-only" % e)
            return self._fallback_results(candidates[:limit], query)

    def _fallback_results(self, candidates, query: str) -> List[PageResult]:
        """Fallback when reranking fails."""
        print("[HindSite SEMANTIC] [fallback] Using vector similarity only (threshold >= 0.35)")
        for i, row in enumerate(candidates):
            print("[HindSite SEMANTIC]   [%d] id=%s url=%s similarity=%.4f" % (i, getattr(row, "id", ""), (getattr(row, "url", "") or "")[:60], getattr(row, "similarity", 0)))
        results = []
        for row in candidates:
            if row.similarity < 0.35:
                continue
            results.append(
                PageResult(
                    id=row.id,
                    url=row.url,
                    title=row.title or self._extract_title(row.url),
                    domain=row.domain or self._extract_title(row.url) or "",
                    snippet=self._extract_snippet(row.content or "", query),
                    similarity=round(row.similarity, 3),
                    time_spent=row.time_spent,
                    captured_at=row.captured_at,
                )
            )
        print("[HindSite SEMANTIC] [fallback] Returning %d results" % len(results))
        print("[HindSite SEMANTIC] ========== Semantic search finished ==========")
        return results

    def _extract_snippet(self, content: str, query: str, length: int = 150) -> str:
        """Extract a relevant snippet from content based on query."""
        if not content:
            return ""

        content_lower = content.lower()
        query_words = query.lower().split()

        best_pos = 0
        for word in query_words:
            if len(word) > 3:
                pos = content_lower.find(word)
                if pos != -1:
                    best_pos = pos
                    break

        start = max(0, best_pos - 30)
        end = min(len(content), start + length)
        snippet = content[start:end].strip()

        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet

    def _extract_title(self, url: str) -> str:
        """Extract a title from URL if none exists."""
        try:
            parsed = urlparse(url)
            return parsed.netloc or url[:50]
        except Exception:
            return url[:50] if url else ""


search_service = SearchService()
