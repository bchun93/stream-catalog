"""Sync TMDB artwork into MediaAsset rows for a title."""

from sqlalchemy.orm import Session

from app.models.media_asset import AssetStatus, AssetType, MediaAsset
from app.models.title import Title
from app.schemas.artwork import ArtworkItem
from app.services.tmdb_service import (
    TMDB_SOURCE_NOTE,
    collect_artwork_from_tmdb,
    parse_external_id,
)

_TMDB_URI_PREFIX = "https://image.tmdb.org/"


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
            language=item.language,
            resolution=item.resolution,
            notes=item.notes,
        )
        db.add(asset)
        created.append(asset)
    return created


async def sync_artwork_for_title(db: Session, title: Title) -> list[MediaAsset]:
    if not _is_tmdb_external_id(title.external_id):
        return []
    media_type, tmdb_id = parse_external_id(title.external_id)
    items = await collect_artwork_from_tmdb(media_type, tmdb_id)
    _clear_tmdb_artwork(db, title.id)
    assets = _persist_artwork(db, title.id, items)
    db.commit()
    for asset in assets:
        db.refresh(asset)
    return assets
