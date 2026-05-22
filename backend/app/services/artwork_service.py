"""Sync TMDB artwork into MediaAsset rows for a title."""

from sqlalchemy.orm import Session

from app.models.media_asset import AssetStatus, AssetType, MediaAsset
from app.models.title import Title
from app.schemas.artwork import ArtworkItem
from app.services.artwork_metadata import artwork_item_metadata_json
from app.services.tmdb_service import (
    TMDB_SOURCE_NOTE,
    collect_artwork_from_tmdb,
    parse_external_id,
)

_TMDB_URI_PREFIX = "https://image.tmdb.org/"

_ARTWORK_TYPES = (
    AssetType.POSTER,
    AssetType.BACKDROP,
    AssetType.LOGO,
    AssetType.STILL,
    AssetType.CAST_PHOTO,
    AssetType.SEASON_POSTER,
)


def _is_tmdb_external_id(external_id: str | None) -> bool:
    return bool(external_id and external_id.startswith("tmdb:"))


async def fetch_artwork_preview(external_id: str) -> list[ArtworkItem]:
    media_type, tmdb_id = parse_external_id(external_id)
    return await collect_artwork_from_tmdb(media_type, tmdb_id)


def _clear_tmdb_artwork(db: Session, title_id: int) -> None:
    db.query(MediaAsset).filter(
        MediaAsset.title_id == title_id,
        MediaAsset.storage_uri.like(f"{_TMDB_URI_PREFIX}%"),
    ).delete(synchronize_session=False)


def _persist_artwork(db: Session, title_id: int, items: list[ArtworkItem]) -> list[MediaAsset]:
    created: list[MediaAsset] = []
    for item in items:
        asset = MediaAsset(
            title_id=title_id,
            asset_type=item.asset_type,
            status=AssetStatus.READY,
            filename=item.filename,
            mime_type=item.mime_type,
            storage_uri=item.storage_uri,
            language=item.language or item.specs.language,
            resolution=item.resolution or item.specs.resolution,
            notes=item.notes,
            metadata_json=artwork_item_metadata_json(item),
        )
        db.add(asset)
        created.append(asset)
    return created


def list_artwork_assets(db: Session, title_id: int) -> list[MediaAsset]:
    return (
        db.query(MediaAsset)
        .filter(
            MediaAsset.title_id == title_id,
            MediaAsset.asset_type.in_(_ARTWORK_TYPES),
        )
        .order_by(MediaAsset.asset_type, MediaAsset.updated_at.desc())
        .all()
    )


def save_artwork_selection(
    db: Session, title_id: int, items: list[ArtworkItem]
) -> list[MediaAsset]:
    """Append selected artwork; skip URIs already in the catalog."""
    if not items:
        return list_artwork_assets(db, title_id)

    existing_uris = {a.storage_uri for a in list_artwork_assets(db, title_id)}
    to_add = [item for item in items if item.storage_uri not in existing_uris]
    if to_add:
        created = _persist_artwork(db, title_id, to_add)
        db.commit()
        for asset in created:
            db.refresh(asset)

    return list_artwork_assets(db, title_id)


async def sync_artwork_for_title(db: Session, title: Title) -> list[MediaAsset]:
    """Fetch all TMDB artwork and save everything (legacy bulk sync)."""
    if not _is_tmdb_external_id(title.external_id):
        return []
    media_type, tmdb_id = parse_external_id(title.external_id)
    items = await collect_artwork_from_tmdb(media_type, tmdb_id)
    return save_artwork_selection(db, title.id, items)
