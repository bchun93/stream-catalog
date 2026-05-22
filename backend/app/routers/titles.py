import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_db
from app.models.title import Title, TitleType
from app.schemas.artwork import SaveArtworkRequest
from app.schemas.media_asset import MediaAssetRead
from app.schemas.title import TitleCreate, TitleRead, TitleTree, TitleUpdate
from app.services import title_service
from app.services.artwork_metadata import enrich_asset_read
from app.services.artwork_service import (
    list_artwork_assets,
    save_artwork_selection,
    sync_artwork_for_title,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/titles", tags=["titles"])


def _title_to_tree(title) -> TitleTree:
    children = getattr(title, "_tree_children", [])
    data = TitleRead.model_validate(title).model_dump()
    return TitleTree(**data, children=[_title_to_tree(c) for c in children])


@router.get("", response_model=list[TitleRead])
def list_titles(
    q: str | None = Query(None, description="Search name or slug"),
    title_type: TitleType | None = None,
    parent_id: int | None = None,
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    try:
        return title_service.list_titles_read(
            db, q=q, title_type=title_type, parent_id=parent_id, skip=skip, limit=limit
        )
    except SQLAlchemyError as exc:
        logger.exception("list_titles failed")
        raise HTTPException(
            status_code=503,
            detail=(
                f"Database error: {exc}. "
                "Verify DATABASE_URL on Render (Neon) and redeploy."
            ),
        ) from exc
    except Exception as exc:
        logger.exception("list_titles unexpected failure")
        raise HTTPException(
            status_code=500,
            detail=f"Could not list titles: {exc}",
        ) from exc


@router.get("/tree", response_model=list[TitleTree])
def get_title_tree(
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    try:
        roots = title_service.build_title_tree(db)
        return [_title_to_tree(r) for r in roots]
    except SQLAlchemyError as exc:
        logger.exception("get_title_tree failed")
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc


@router.post("", response_model=TitleRead, status_code=201)
def create_title(
    payload: TitleCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    try:
        existing = db.query(Title).filter(Title.slug == payload.slug).first()
        if existing:
            raise HTTPException(status_code=409, detail="Slug already exists")
        title = title_service.create_title(db, payload)
        read = title_service.get_title_read(db, title.id)
        return read or TitleRead.model_validate(title)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("create_title failed")
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc


@router.get("/{title_id}/artwork", response_model=list[MediaAssetRead])
def list_title_artwork(
    title_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    assets = list_artwork_assets(db, title_id)
    return [enrich_asset_read(a) for a in assets]


@router.post("/{title_id}/artwork", response_model=list[MediaAssetRead])
def save_title_artwork(
    title_id: int,
    payload: SaveArtworkRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    try:
        assets = save_artwork_selection(db, title_id, payload.items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [enrich_asset_read(a) for a in assets]


@router.post("/{title_id}/artwork/sync", response_model=list[MediaAssetRead])
async def sync_title_artwork(
    title_id: int,
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
    assets = await sync_artwork_for_title(db, title)
    return [enrich_asset_read(a) for a in assets]


@router.get("/{title_id}", response_model=TitleRead)
def get_title(
    title_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    title = title_service.get_title_read(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    return title


@router.patch("/{title_id}", response_model=TitleRead)
def update_title(
    title_id: int,
    payload: TitleUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    title_service.update_title(db, title, payload)
    read = title_service.get_title_read(db, title_id)
    return read or TitleRead.model_validate(title)


@router.delete("/{title_id}", status_code=204)
def delete_title(
    title_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    title_service.delete_title(db, title)
    return None
