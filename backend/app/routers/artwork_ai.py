from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_db
from app.schemas.artwork_ai import (
    ArtworkAutoAssignRequest,
    ArtworkAutoAssignResponse,
    ArtworkClassifyResponse,
    ArtworkLabelRequest,
    ArtworkReviewItem,
    ArtworkTrainingExampleRead,
)
from app.services import artwork_classifier, title_service

router = APIRouter(tags=["artwork-ai"])


@router.post(
    "/titles/{title_id}/artwork/classify",
    response_model=ArtworkClassifyResponse,
)
async def classify_title_artwork(
    title_id: int,
    threshold: float = Query(0.9, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    if not title.external_id or not title.external_id.startswith("tmdb:"):
        raise HTTPException(
            status_code=400,
            detail="Title has no TMDB external_id — import metadata first",
        )
    predictions = await artwork_classifier.classify_title_artwork(
        db, title, threshold=threshold
    )
    return ArtworkClassifyResponse(
        title_id=title_id,
        threshold=threshold,
        predictions=predictions,
    )


@router.post(
    "/titles/{title_id}/artwork/auto-assign",
    response_model=ArtworkAutoAssignResponse,
)
async def auto_assign_title_artwork(
    title_id: int,
    payload: ArtworkAutoAssignRequest | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    if not title.external_id or not title.external_id.startswith("tmdb:"):
        raise HTTPException(
            status_code=400,
            detail="Title has no TMDB external_id — import metadata first",
        )
    threshold = payload.threshold if payload else 0.9
    return await artwork_classifier.auto_assign_title_artwork(
        db, title, threshold=threshold
    )


@router.post(
    "/artwork-ai/labels",
    response_model=ArtworkTrainingExampleRead,
    status_code=201,
)
def record_artwork_label(
    payload: ArtworkLabelRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    if payload.title_id and not title_service.get_title(db, payload.title_id):
        raise HTTPException(status_code=404, detail="Title not found")
    return artwork_classifier.record_label(db, payload)


@router.get("/artwork-ai/review", response_model=list[ArtworkReviewItem])
def artwork_review_queue(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    return artwork_classifier.review_queue(db, limit=limit)
