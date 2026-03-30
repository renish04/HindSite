"""
Topic Classification API Endpoints

This module provides REST API endpoints for the topic discovery system.
These endpoints allow the frontend to:
- Trigger model training
- Get pages organized by topics
- Classify new pages
- Check model status and health
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..database import get_db
from ..models import CapturedPage
from ..services.topic_model import TopicModel, TopicService

# Create router
router = APIRouter(prefix="/topics", tags=["topics"])

# Initialize the topic service (singleton)
topic_service = TopicService()


# ============================================================
# Pydantic Models for Request/Response
# ============================================================

class TrainRequest(BaseModel):
    """Request body for training endpoint."""
    force_retrain: bool = False


class TrainResponse(BaseModel):
    """Response from training endpoint."""
    success: bool
    message: str
    n_topics: Optional[int] = None
    pages_trained: Optional[int] = None
    topics: Optional[dict] = None
    error: Optional[str] = None


class TopicInfo(BaseModel):
    """Information about a single topic."""
    id: int
    label: str
    page_count: int
    top_words: List[str]
    top_domains: List[str]
    sample_titles: List[str]


class ClassifyRequest(BaseModel):
    """Request to classify a page."""
    page_id: str


class ClassifyResponse(BaseModel):
    """Response from classification."""
    success: bool
    page_id: str
    topic_label: Optional[str] = None
    confidence: Optional[float] = None
    is_outlier: bool = False
    all_probabilities: Optional[dict] = None
    error: Optional[str] = None


class ModelStatusResponse(BaseModel):
    """Response with model status."""
    is_trained: bool
    n_topics: Optional[int] = None
    training_timestamp: Optional[str] = None
    pages_at_training: Optional[int] = None
    outlier_buffer_size: int = 0
    topics: Optional[dict] = None


class PageWithTopic(BaseModel):
    """Page data including topic information."""
    id: str
    url: str
    title: str
    domain: str
    topic_label: str
    topic_confidence: float
    is_outlier: bool
    captured_at: datetime
    thumbnail_base64: Optional[str] = None


class TopicWithPages(BaseModel):
    """A topic with its associated pages."""
    topic_label: str
    page_count: int
    pages: List[dict]


# ============================================================
# Helper Functions
# ============================================================

def get_all_pages_with_embeddings(db: Session) -> List[dict]:
    """
    Fetch all pages that have embeddings from the database.
    
    Returns list of dictionaries with page data including embeddings.
    """
    pages = db.query(CapturedPage).filter(
        CapturedPage.embedding.isnot(None)
    ).order_by(CapturedPage.captured_at.desc()).all()
    
    return [
        {
            "id": str(page.id),
            "url": page.url,
            "title": page.title or "",
            "domain": page.domain or "",
            "content": page.content or "",
            "embedding": page.embedding,
            "captured_at": page.captured_at,
            "thumbnail": page.thumbnail
        }
        for page in pages
    ]


def page_to_response_dict(page: dict, include_thumbnail: bool = False) -> dict:
    """Convert internal page dict to API response format."""
    import base64
    
    result = {
        "id": page["id"],
        "url": page["url"],
        "title": page["title"],
        "domain": page["domain"],
        "topic_label": page.get("topic_label", "Uncategorized"),
        "topic_confidence": page.get("topic_confidence", 0.0),
        "is_outlier": page.get("is_outlier", False),
        "captured_at": page["captured_at"].isoformat() if page.get("captured_at") else None
    }
    
    if include_thumbnail and page.get("thumbnail"):
        result["thumbnail_base64"] = base64.b64encode(page["thumbnail"]).decode('utf-8')
    
    return result


# ============================================================
# API Endpoints
# ============================================================

@router.post("/train", response_model=TrainResponse)
async def train_topic_model(
    request: TrainRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Train the topic model on all captured pages.
    
    This endpoint triggers training of the GMM-based topic discovery system.
    Training discovers natural topic clusters in the user's browsing history.
    
    The model learns:
    - How many topics exist in the browsing history
    - The "center" and "shape" of each topic in embedding space
    - Labels for each topic based on page titles and domains
    
    Query Parameters:
    - force_retrain: If true, retrain even if a model exists
    
    Returns:
    - Training results including discovered topics
    """
    # Get all pages with embeddings
    pages = get_all_pages_with_embeddings(db)
    
    if len(pages) < 20:
        return TrainResponse(
            success=False,
            message=f"Need at least 20 pages to train. Currently have {len(pages)}.",
            error="insufficient_pages"
        )
    
    # Check if we should retrain
    if not request.force_retrain and topic_service.model.is_trained:
        should_retrain, reason = topic_service.model.should_retrain(len(pages))
        if not should_retrain:
            return TrainResponse(
                success=True,
                message=f"Model already trained and up-to-date. {reason}",
                n_topics=topic_service.model.n_clusters,
                pages_trained=topic_service.model.pages_at_training
            )
    
    # Train the model
    result = topic_service.train_from_pages(pages)
    
    if result["success"]:
        return TrainResponse(
            success=True,
            message=f"Successfully trained model with {result['n_clusters']} topics",
            n_topics=result["n_clusters"],
            pages_trained=result["pages_trained"],
            topics=result["topics"]
        )
    else:
        return TrainResponse(
            success=False,
            message="Training failed",
            error=result.get("error", "Unknown error")
        )


@router.get("/status", response_model=ModelStatusResponse)
async def get_model_status():
    """
    Get the current status of the topic model.
    
    Returns information about:
    - Whether the model is trained
    - Number of discovered topics
    - When the model was trained
    - How many pages it was trained on
    - Topic details
    """
    # Try to load model if not in memory
    if not topic_service.model.is_trained:
        topic_service.model.load_model()
    
    status = topic_service.get_model_status()
    
    return ModelStatusResponse(
        is_trained=status.get("is_trained", False),
        n_topics=status.get("n_topics"),
        training_timestamp=status.get("training_timestamp"),
        pages_at_training=status.get("pages_at_training"),
        outlier_buffer_size=status.get("outlier_buffer_size", 0),
        topics=status.get("topics")
    )


@router.get("/pages", response_model=List[TopicWithPages])
async def get_pages_by_topic(
    include_thumbnails: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get all pages organized by their topics.
    
    This endpoint:
    1. Loads the trained model (or returns uncategorized if no model)
    2. Classifies all pages into topics
    3. Returns pages grouped by topic
    
    Each topic includes:
    - Topic label (auto-generated name)
    - Page count
    - List of pages with their confidence scores
    
    Query Parameters:
    - include_thumbnails: If true, include base64 thumbnails (larger response)
    """
    # Try to load model if not trained
    if not topic_service.model.is_trained:
        topic_service.model.load_model()
    
    # Get all pages
    pages = get_all_pages_with_embeddings(db)
    
    if not pages:
        return []
    
    # Organize by topic
    organized = topic_service.get_pages_by_topic(pages)
    
    # Convert to response format
    result = []
    for topic_label, topic_pages in organized.items():
        result.append(TopicWithPages(
            topic_label=topic_label,
            page_count=len(topic_pages),
            pages=[
                page_to_response_dict(p, include_thumbnails) 
                for p in topic_pages
            ]
        ))
    
    # Sort by page count (largest topics first)
    result.sort(key=lambda x: x.page_count, reverse=True)
    
    return result


@router.post("/classify/{page_id}", response_model=ClassifyResponse)
async def classify_single_page(
    page_id: str,
    db: Session = Depends(get_db)
):
    """
    Classify a single page into a topic.
    
    This endpoint:
    1. Fetches the page by ID
    2. Runs it through the trained model
    3. Returns the predicted topic and confidence
    
    If the page doesn't fit any topic well (outlier), it will be:
    - Marked as is_outlier=True
    - Added to the outlier buffer
    - May trigger retraining if too many outliers accumulate
    
    Path Parameters:
    - page_id: The unique ID of the page to classify
    """
    # Check model is trained
    if not topic_service.model.is_trained:
        topic_service.model.load_model()
    
    if not topic_service.model.is_trained:
        return ClassifyResponse(
            success=False,
            page_id=page_id,
            error="Model not trained. Call /topics/train first."
        )
    
    # Fetch the page
    page = db.query(CapturedPage).filter(CapturedPage.id == page_id).first()
    
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    if page.embedding is None:
        return ClassifyResponse(
            success=False,
            page_id=page_id,
            error="Page has no embedding"
        )
    
    # Classify
    page_dict = {
        "id": str(page.id),
        "title": page.title,
        "domain": page.domain,
        "embedding": page.embedding
    }
    
    result = topic_service.classify_page(page_dict)
    
    if result["success"]:
        return ClassifyResponse(
            success=True,
            page_id=page_id,
            topic_label=result["predicted_topic_label"],
            confidence=result["confidence"],
            is_outlier=result["is_outlier"],
            all_probabilities=result["all_probabilities"]
        )
    else:
        return ClassifyResponse(
            success=False,
            page_id=page_id,
            error=result.get("error", "Classification failed")
        )


@router.get("/topics", response_model=List[TopicInfo])
async def list_topics():
    """
    List all discovered topics with their metadata.
    
    Returns a list of topics with:
    - Topic ID and label
    - Page count
    - Top words found in page titles
    - Top domains
    - Sample page titles
    """
    if not topic_service.model.is_trained:
        topic_service.model.load_model()
    
    if not topic_service.model.is_trained:
        return []
    
    topics = []
    for cluster_id in range(topic_service.model.n_clusters):
        label = topic_service.model.topic_labels.get(cluster_id, f"Topic {cluster_id}")
        metadata = topic_service.model.topic_metadata.get(cluster_id, {})
        
        topics.append(TopicInfo(
            id=cluster_id,
            label=label,
            page_count=metadata.get("page_count", 0),
            top_words=metadata.get("top_words", []),
            top_domains=metadata.get("top_domains", []),
            sample_titles=metadata.get("sample_titles", [])
        ))
    
    return topics


@router.post("/auto-organize")
async def auto_organize(
    db: Session = Depends(get_db)
):
    """
    Automatically organize all pages: train if needed, then classify all.
    
    This is a convenience endpoint that:
    1. Checks if training is needed
    2. Trains the model if necessary
    3. Returns all pages organized by topic
    
    Use this for a "one-click" organization feature in the UI.
    """
    pages = get_all_pages_with_embeddings(db)
    
    if len(pages) < 20:
        return {
            "success": False,
            "message": f"Need at least 20 pages. Have {len(pages)}.",
            "pages_count": len(pages)
        }
    
    # Train or retrain if needed
    train_result = topic_service.check_and_retrain(pages)
    
    # Organize pages
    organized = topic_service.get_pages_by_topic(pages)
    
    return {
        "success": True,
        "training_performed": train_result.get("success", False),
        "n_topics": topic_service.model.n_clusters,
        "topics": {
            label: {
                "count": len(topic_pages),
                "pages": [
                    {
                        "id": p["id"],
                        "title": p["title"],
                        "domain": p["domain"],
                        "confidence": p.get("topic_confidence", 0)
                    }
                    for p in topic_pages
                ]
            }
            for label, topic_pages in organized.items()
        }
    }


@router.delete("/model")
async def delete_model():
    """
    Delete the trained model and reset to untrained state.
    
    Use this to force a fresh training from scratch.
    """
    import os
    
    model_path = os.path.join(topic_service.model.model_save_path, "topic_model_default.pkl")
    
    if os.path.exists(model_path):
        os.remove(model_path)
    
    # Reset in-memory model
    topic_service.model = TopicModel()
    
    return {
        "success": True,
        "message": "Model deleted. Next call to /train will create a fresh model."
    }

