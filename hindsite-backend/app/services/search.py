import os
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from dotenv import load_dotenv
import cohere

from app.schemas import PageResult
from app.services.embeddings import embedder

load_dotenv()


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

        # Step 2: Vector search (pgvector)
        print("[HindSite SEMANTIC] [vector] Running pgvector similarity search (candidate_limit=%d)" % candidate_limit)
        sql = text("""
            SELECT id, url, title, domain, content, time_spent, scroll_percent, captured_at,
                   1 - (embedding <=> CAST(:embedding AS vector)) as similarity
            FROM captured_pages
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        result = db.execute(
            sql,
            {"embedding": str(query_embedding), "limit": candidate_limit},
        )
        candidates = result.fetchall()

        print("[HindSite SEMANTIC] [vector] Candidates returned: %d" % len(candidates))
        for i, row in enumerate(candidates):
            print("[HindSite SEMANTIC]   [%d] id=%s url=%s similarity=%.4f" % (i, getattr(row, "id", ""), (getattr(row, "url", "") or "")[:60], getattr(row, "similarity", 0)))

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
