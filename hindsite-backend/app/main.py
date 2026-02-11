import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import CapturedPage
from app.schemas import PageCapture, PageResult, SearchQuery, SearchResponse
from app.services.embeddings import embedder
from app.services.router import query_router
from app.services.search import search_service
from app.utils import clean_content, extract_domain, extract_title_from_content

logger = logging.getLogger(__name__)

# Create tables on startup if the DB user has CREATE on schema public.
# If you get "permission denied for schema public", either:
# - Run as DB superuser: GRANT CREATE ON SCHEMA public TO your_app_user;
# - Or create the table (and enable pgvector) yourself, then restart the app.
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    logger.warning("Table create_all failed (tables may already exist or user lacks CREATE): %s", e)

app = FastAPI(title="HindSite API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "HindSite API is running"}


@app.post("/capture")
def capture_page(page: PageCapture, db: Session = Depends(get_db)):
    """Capture a page with embedding generation."""
    existing = db.query(CapturedPage).filter(CapturedPage.url == page.url).first()
    if existing:
        return {"status": "exists", "id": existing.id}

    content = clean_content(page.content)

    try:
        embedding = embedder.generate_document_embedding(content)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Embedding generation failed: {str(e)}"
        )

    db_page = CapturedPage(
        url=page.url,
        title=extract_title_from_content(content, page.url),
        content=content,
        domain=extract_domain(page.url),
        time_spent=page.metadata.get("timeSpent", 0),
        scroll_percent=page.metadata.get("scrollPercent", 0),
        word_count=page.metadata.get("wordCount", 0),
        embedding=embedding,
    )

    db.add(db_page)
    db.commit()
    db.refresh(db_page)

    return {"status": "captured", "id": db_page.id, "title": db_page.title}


@app.post("/search", response_model=SearchResponse)
def search(query: SearchQuery, db: Session = Depends(get_db)):
    """
    Unified search: tab_switch (match open tabs) or semantic_search (vector + rerank).
    """
    intent = query_router.detect_intent(query.query)

    if intent == "tab_switch" and query.open_tabs:
        matched_tab = query_router.find_matching_tab(query.query, query.open_tabs)
        if matched_tab:
            return SearchResponse(
                query_type="tab_switch",
                matched_tab=matched_tab,
                results=None,
            )
        intent = "semantic_search"

    results = search_service.search_pages(
        query.query, db, limit=query.limit or 3
    )
    return SearchResponse(
        query_type="semantic_search",
        results=results,
        matched_tab=None,
    )


@app.get("/pages")
def list_pages(limit: int = 50, db: Session = Depends(get_db)):
    """List recently captured pages."""
    pages = (
        db.query(CapturedPage)
        .order_by(CapturedPage.captured_at.desc())
        .limit(limit)
        .all()
    )
    return [
        PageResult(
            id=p.id,
            url=p.url,
            title=p.title,
            domain=p.domain or "",
            snippet=(
                (p.content[:150] + "...")
                if p.content and len(p.content) > 150
                else (p.content or "")
            ),
            similarity=1.0,
            time_spent=p.time_spent,
            captured_at=p.captured_at,
        )
        for p in pages
    ]


@app.delete("/pages/{page_id}")
def delete_page(page_id: str, db: Session = Depends(get_db)):
    """Delete a captured page."""
    page = db.query(CapturedPage).filter(CapturedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    db.delete(page)
    db.commit()
    return {"status": "deleted", "id": page_id}
