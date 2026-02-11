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
        self.cohere_client = cohere.Client(os.getenv("COHERE_API_KEY"))

    def search_pages(self, query: str, db: Session, limit: int = 3) -> List[PageResult]:
        """
        Two-stage retrieval:
        1. Vector search with pgvector (retrieve top 20 candidates)
        2. Cross-encoder reranking with Cohere Rerank (return top 3)
        """
        query_embedding = embedder.generate_query_embedding(query)
        candidate_limit = max(20, limit * 5)

        sql = text("""
            SELECT id, url, title, domain, content, time_spent, scroll_percent, captured_at,
                   1 - (embedding <=> :embedding::vector) as similarity
            FROM captured_pages
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """)

        result = db.execute(
            sql,
            {"embedding": str(query_embedding), "limit": candidate_limit},
        )
        candidates = result.fetchall()

        if not candidates:
            return []

        documents = [row.content[:2000] if row.content else "" for row in candidates]

        try:
            rerank_response = self.cohere_client.rerank(
                model="rerank-english-v3.0",
                query=query,
                documents=documents,
                top_n=limit,
                return_documents=False,
            )

            results = []
            for rerank_result in rerank_response.results:
                if rerank_result.relevance_score < 0.3:
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

            return results

        except Exception as e:
            print(f"Reranking failed: {e}, falling back to vector search")
            return self._fallback_results(candidates[:limit], query)

    def _fallback_results(self, candidates, query: str) -> List[PageResult]:
        """Fallback when reranking fails."""
        results = []
        for row in candidates:
            if row.similarity < 0.5:
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
