from sqlalchemy.orm import Session

from app.models.media_asset import AssetStatus, AssetType, MediaAsset
from app.schemas.media_asset import MediaAssetCreate, MediaAssetUpdate


def list_assets(
    db: Session,
    *,
    title_id: int | None = None,
    asset_type: AssetType | None = None,
    status: AssetStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[MediaAsset]:
    query = db.query(MediaAsset)
    if title_id is not None:
        query = query.filter(MediaAsset.title_id == title_id)
    if asset_type:
        query = query.filter(MediaAsset.asset_type == asset_type)
    if status:
        query = query.filter(MediaAsset.status == status)
    return query.order_by(MediaAsset.updated_at.desc()).offset(skip).limit(limit).all()


def get_asset(db: Session, asset_id: int) -> MediaAsset | None:
    return db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()


def create_asset(db: Session, payload: MediaAssetCreate) -> MediaAsset:
    asset = MediaAsset(**payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(db: Session, asset: MediaAsset, payload: MediaAssetUpdate) -> MediaAsset:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, key, value)
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset: MediaAsset) -> None:
    db.delete(asset)
    db.commit()
