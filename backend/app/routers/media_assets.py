from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.media_asset import AssetStatus, AssetType
from app.models.title import Title
from app.schemas.media_asset import MediaAssetCreate, MediaAssetRead, MediaAssetUpdate
from app.services import media_service
from app.services.artwork_metadata import enrich_asset_read

router = APIRouter(prefix="/assets", tags=["media-assets"])


@router.get("", response_model=list[MediaAssetRead])
def list_assets(
    title_id: int | None = None,
    asset_type: AssetType | None = None,
    status: AssetStatus | None = None,
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    assets = media_service.list_assets(
        db,
        title_id=title_id,
        asset_type=asset_type,
        status=status,
        skip=skip,
        limit=limit,
    )
    return [enrich_asset_read(a) for a in assets]


@router.get("/{asset_id}", response_model=MediaAssetRead)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = media_service.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return enrich_asset_read(asset)


@router.post("", response_model=MediaAssetRead, status_code=201)
def create_asset(payload: MediaAssetCreate, db: Session = Depends(get_db)):
    title = db.query(Title).filter(Title.id == payload.title_id).first()
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    return enrich_asset_read(media_service.create_asset(db, payload))


@router.patch("/{asset_id}", response_model=MediaAssetRead)
def update_asset(
    asset_id: int, payload: MediaAssetUpdate, db: Session = Depends(get_db)
):
    asset = media_service.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return enrich_asset_read(media_service.update_asset(db, asset, payload))


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = media_service.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    media_service.delete_asset(db, asset)
    return None
