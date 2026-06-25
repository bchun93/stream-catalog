import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db_repair import retry_after_enum_repair
from app.database import get_db
from app.deps import require_admin_token, require_db
from app.services.artwork_fetch import fetch_tmdb_artwork
from app.models.media_asset import MediaAsset
from app.models.title import Title, TitleType
from app.schemas.artwork import SaveArtworkRequest
from app.schemas.media_asset import MediaAssetRead
from app.schemas.title import TitleCreate, TitleRead, TitleTree, TitleUpdate
from app.services import title_service
from app.services.artwork_metadata import enrich_asset_read
from app.services.artwork_service import (
    clear_all_artwork_assets,
    delete_artwork_asset,
    list_artwork_assets,
    save_artwork_selection,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/titles", tags=["titles"])


def _download_filename(value: str | None, fallback: str) -> str:
    raw = (value or fallback).split("/")[-1].strip() or fallback
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw)[:180]


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
        return retry_after_enum_repair(
            db,
            lambda: title_service.list_titles_read(
                db, q=q, title_type=title_type, parent_id=parent_id, skip=skip, limit=limit
            ),
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
        roots = retry_after_enum_repair(db, lambda: title_service.build_title_tree(db))
        return [_title_to_tree(r) for r in roots]
    except SQLAlchemyError as exc:
        logger.exception("get_title_tree failed")
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc


@router.post("", response_model=TitleRead, status_code=201)
def create_title(
    payload: TitleCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
    __: None = Depends(require_admin_token),
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@router.delete("/{title_id}/artwork", status_code=200)
def clear_title_artwork(
    title_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
    __: None = Depends(require_admin_token),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    removed = clear_all_artwork_assets(db, title_id)
    return {"removed": removed}


@router.delete("/{title_id}/artwork/{asset_id}", status_code=204)
def delete_title_artwork(
    title_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
    __: None = Depends(require_admin_token),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    try:
        delete_artwork_asset(db, title_id, asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return None


@router.get("/{title_id}/artwork/{asset_id}/download")
def download_title_artwork(
    title_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.id == asset_id, MediaAsset.title_id == title_id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Artwork asset not found")
    try:
        content, fetched_type = fetch_tmdb_artwork(asset.storage_uri)
    except ValueError:
        raise HTTPException(status_code=400, detail="Artwork URI is not allowed") from None
    except Exception:
        logger.exception("Artwork download failed for asset %s", asset_id)
        raise HTTPException(status_code=502, detail="Could not download artwork") from None

    filename = _download_filename(asset.filename, f"artwork-{asset.id}.jpg")
    media_type = asset.mime_type or fetched_type or "application/octet-stream"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{title_id}/artwork", response_model=list[MediaAssetRead])
def save_title_artwork(
    title_id: int,
    payload: SaveArtworkRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
    __: None = Depends(require_admin_token),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    try:
        assets = save_artwork_selection(db, title_id, payload.items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    __: None = Depends(require_admin_token),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    try:
        title_service.update_title(db, title, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    read = title_service.get_title_read(db, title_id)
    return read or TitleRead.model_validate(title)


@router.delete("/{title_id}", status_code=204)
def delete_title(
    title_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
    __: None = Depends(require_admin_token),
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    title_service.delete_title(db, title)
    return None
