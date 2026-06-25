"""Sync TMDB artwork into MediaAsset rows for a title."""

import json
import logging

from sqlalchemy.orm import Session

from app.models.media_asset import AssetStatus, AssetType, MediaAsset
from app.models.title import Title, TitleType
from app.schemas.artwork import ArtworkItem, ArtworkSpecs
from app.services.artwork_metadata import artwork_item_metadata_json
from app.services.poster_resolver import is_allowed_tmdb_artwork_uri, is_usable_poster_url
from app.services.title_service import sync_title_poster_cache
from app.services.tmdb_service import (
    TMDB_SOURCE_NOTE,
    _artwork_filename,
    collect_artwork_from_tmdb,
    parse_external_id,
)

logger = logging.getLogger(__name__)

_TMDB_URI_PREFIX = "https://image.tmdb.org/"

_ARTWORK_TYPES = (
    AssetType.POSTER,
    AssetType.BACKDROP,
    AssetType.LOGO,
    AssetType.STILL,
    AssetType.CAST_PHOTO,
    AssetType.SEASON_POSTER,
)

_CORE_ARTWORK_LABELS = {
    "h_poster": "Horizontal poster",
    "still_frame": "Still frame",
    "v_poster": "Vertical poster",
    "logo": "Logo",
    "hero_image": "Hero image",
    "hero_image_vertical": "Hero image vertical",
    "box_art": "Box art",
}


def _preferred_artwork_label(item: ArtworkItem, labels: list[str]) -> str:
    """Pick the best single catalog role when core metadata reuses one TMDB file."""
    specs = item.specs
    aspect = specs.aspect_ratio if specs else None

    if item.asset_type in (AssetType.POSTER, AssetType.SEASON_POSTER):
        if "Vertical poster" in labels:
            return "Vertical poster"
        if "Box art" in labels:
            return "Box art"
    if item.asset_type == AssetType.BACKDROP or (aspect is not None and aspect >= 1.6):
        if "Hero image" in labels:
            return "Hero image"
        if "Horizontal poster" in labels:
            return "Horizontal poster"
    if item.asset_type == AssetType.STILL and "Still frame" in labels:
        return "Still frame"
    if item.asset_type == AssetType.LOGO and "Logo" in labels:
        return "Logo"
    return labels[0]


def _is_tmdb_external_id(external_id: str | None) -> bool:
    return bool(external_id and external_id.startswith("tmdb:"))


def can_fetch_tmdb_artwork_library(external_id: str | None) -> bool:
    """True for root TMDB movie/series ids that support the /images fetch."""
    if not external_id or not external_id.startswith("tmdb:"):
        return False
    parts = external_id.split(":")
    return len(parts) == 3 and parts[1] in ("movie", "tv")


def _uri_basename(uri: str) -> str:
    return uri.split("?", 1)[0].rstrip("/").split("/")[-1]


def _metadata_artwork_labels(metadata_json: str | None) -> dict[str, list[str]]:
    if not metadata_json:
        return {}
    try:
        raw = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    labels_by_filename: dict[str, list[str]] = {}
    for key, label in _CORE_ARTWORK_LABELS.items():
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        filename = value.strip().split("/")[-1]
        labels = labels_by_filename.setdefault(filename, [])
        if label not in labels:
            labels.append(label)
    return labels_by_filename


def _with_artwork_label(item: ArtworkItem, labels: list[str]) -> ArtworkItem:
    label = _preferred_artwork_label(item, labels)
    specs = item.specs or ArtworkSpecs()
    specs = specs.model_copy(update={"label": label})
    note = f"{TMDB_SOURCE_NOTE}; {label}"
    if item.language and item.language != "en":
        note = f"{note}; lang:{item.language}"
    return item.model_copy(
        update={
            "asset_type": AssetType.POSTER,
            "notes": note,
            "specs": specs,
        }
    )


def _labels_for_artwork_item(
    item: ArtworkItem, labels_by_filename: dict[str, list[str]]
) -> list[str] | None:
    labels = labels_by_filename.get(_uri_basename(item.storage_uri))
    if labels:
        return labels
    item_fn = item.filename.rsplit("/", 1)[-1]
    labels = labels_by_filename.get(item_fn)
    if labels:
        return labels
    for meta_fn, meta_labels in labels_by_filename.items():
        if item_fn == meta_fn or item_fn.endswith(f"_{meta_fn}"):
            return meta_labels
    return None


def _filter_to_metadata_artwork(
    items: list[ArtworkItem], metadata_json: str | None
) -> list[ArtworkItem]:
    labels_by_filename = _metadata_artwork_labels(metadata_json)
    if not labels_by_filename:
        return []

    selected: dict[str, ArtworkItem] = {}
    for item in items:
        labels = _labels_for_artwork_item(item, labels_by_filename)
        if not labels:
            continue
        if item.storage_uri not in selected:
            selected[item.storage_uri] = _with_artwork_label(item, labels)
    return list(selected.values())


def _reference_artwork_source_type(title: Title) -> AssetType:
    if title.title_type == TitleType.EPISODE:
        return AssetType.STILL
    if title.title_type == TitleType.SEASON:
        return AssetType.SEASON_POSTER
    return AssetType.POSTER


def _reference_artwork_items(title: Title) -> list[ArtworkItem]:
    """Build catalog artwork from a title's poster/still URL and core metadata filenames."""
    if not title.poster_url or not title.metadata_json:
        return []
    labels_by_filename = _metadata_artwork_labels(title.metadata_json)
    if not labels_by_filename:
        return []

    uri = title.poster_url.strip()
    basename = _uri_basename(uri)
    labels = labels_by_filename.get(basename)
    if not labels:
        for meta_fn, meta_labels in labels_by_filename.items():
            if meta_fn in uri:
                labels = meta_labels
                basename = meta_fn
                break
    if not labels or not is_usable_poster_url(uri):
        return []

    source_type = _reference_artwork_source_type(title)
    item = ArtworkItem(
        asset_type=source_type,
        storage_uri=uri,
        filename=_artwork_filename(source_type, basename, "en"),
        mime_type="image/jpeg",
        notes=f"{TMDB_SOURCE_NOTE}; {labels[0]}",
        specs=ArtworkSpecs(label=labels[0]),
    )
    return [_with_artwork_label(item, labels)]


async def fetch_artwork_preview(external_id: str) -> list[ArtworkItem]:
    media_type, tmdb_id = parse_external_id(external_id)
    return await collect_artwork_from_tmdb(media_type, tmdb_id)


def _clear_tmdb_artwork(db: Session, title_id: int) -> None:
    db.query(MediaAsset).filter(
        MediaAsset.title_id == title_id,
        MediaAsset.storage_uri.like(f"{_TMDB_URI_PREFIX}%"),
    ).delete(synchronize_session=False)


def _replace_tmdb_artwork(
    db: Session, title_id: int, items: list[ArtworkItem]
) -> list[MediaAsset]:
    if not items:
        return list_artwork_assets(db, title_id)
    _clear_tmdb_artwork(db, title_id)
    created = _persist_artwork(db, title_id, items)
    db.commit()
    sync_title_poster_cache(db, title_id)
    return list_artwork_assets(db, title_id)


def _persist_artwork(db: Session, title_id: int, items: list[ArtworkItem]) -> list[MediaAsset]:
    created: list[MediaAsset] = []
    for item in items:
        if not is_allowed_tmdb_artwork_uri(item.storage_uri):
            continue
        if item.asset_type == AssetType.POSTER and not is_usable_poster_url(
            item.storage_uri
        ):
            continue
        specs = item.specs
        asset = MediaAsset(
            title_id=title_id,
            asset_type=item.asset_type,
            status=AssetStatus.READY,
            filename=item.filename,
            mime_type=item.mime_type,
            storage_uri=item.storage_uri,
            language=item.language or (specs.language if specs else None),
            resolution=item.resolution or (specs.resolution if specs else None),
            notes=item.notes,
            metadata_json=artwork_item_metadata_json(item),
        )
        db.add(asset)
        created.append(asset)
    return created


def list_artwork_assets(db: Session, title_id: int) -> list[MediaAsset]:
    assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.title_id == title_id)
        .order_by(MediaAsset.updated_at.desc())
        .all()
    )
    return [asset for asset in assets if asset.asset_type in _ARTWORK_TYPES]


def save_artwork_selection(
    db: Session, title_id: int, items: list[ArtworkItem]
) -> list[MediaAsset]:
    """Append selected artwork; skip URIs already in the catalog."""
    if not items:
        return list_artwork_assets(db, title_id)

    existing_assets = list_artwork_assets(db, title_id)
    existing_by_uri = {a.storage_uri: a for a in existing_assets}
    to_add = [item for item in items if item.storage_uri not in existing_by_uri]
    for item in items:
        asset = existing_by_uri.get(item.storage_uri)
        if not asset:
            continue
        if item.notes and asset.notes != item.notes:
            asset.notes = item.notes
        metadata_json = artwork_item_metadata_json(item)
        if metadata_json and asset.metadata_json != metadata_json:
            asset.metadata_json = metadata_json
    if to_add:
        created = _persist_artwork(db, title_id, to_add)
        if not created:
            raise ValueError(
                "None of the selected images could be saved. "
                "Choose valid TMDB artwork (not placeholder URLs)."
            )
        db.commit()
        sync_title_poster_cache(db, title_id)
    elif existing_assets:
        db.commit()

    return list_artwork_assets(db, title_id)


def delete_artwork_asset(db: Session, title_id: int, asset_id: int) -> None:
    """Remove a saved artwork asset from a title's catalog."""
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.id == asset_id, MediaAsset.title_id == title_id)
        .first()
    )
    if not asset:
        raise ValueError("Artwork asset not found")
    if asset.asset_type not in _ARTWORK_TYPES:
        raise ValueError("Asset is not catalog artwork")

    deleted_uri = asset.storage_uri
    title = db.query(Title).filter(Title.id == title_id).first()
    was_title_poster = bool(title and title.poster_url == deleted_uri)

    db.delete(asset)
    db.commit()
    sync_title_poster_cache(db, title_id)
    if was_title_poster:
        title = db.query(Title).filter(Title.id == title_id).first()
        if title and title.poster_url == deleted_uri:
            title.poster_url = None
            db.commit()


def clear_all_artwork_assets(db: Session, title_id: int) -> int:
    """Remove every saved artwork asset from a title's catalog."""
    assets = list_artwork_assets(db, title_id)
    if not assets:
        return 0

    deleted_uris = {asset.storage_uri for asset in assets}
    title = db.query(Title).filter(Title.id == title_id).first()
    poster_uri = title.poster_url if title else None

    for asset in assets:
        db.delete(asset)
    db.commit()
    sync_title_poster_cache(db, title_id)
    if title and poster_uri and poster_uri in deleted_uris:
        db.refresh(title)
        if title.poster_url in deleted_uris:
            title.poster_url = None
            db.commit()

    return len(assets)


async def sync_artwork_for_title(db: Session, title: Title) -> list[MediaAsset]:
    """Fetch TMDB artwork and save only images referenced by core metadata."""
    if not can_fetch_tmdb_artwork_library(title.external_id):
        return []
    title_id = title.id
    metadata_json = title.metadata_json
    media_type, tmdb_id = parse_external_id(title.external_id)
    items = await collect_artwork_from_tmdb(media_type, tmdb_id)
    matching_items = _filter_to_metadata_artwork(items, metadata_json)
    db.rollback()
    return _replace_tmdb_artwork(db, title_id, matching_items)


async def auto_sync_artwork_for_title(db: Session, title: Title) -> list[MediaAsset]:
    """Sync artwork for a TMDB title using the images API or a reference still/poster URL."""
    if not _is_tmdb_external_id(title.external_id):
        return list_artwork_assets(db, title.id)
    title_id = title.id
    if can_fetch_tmdb_artwork_library(title.external_id):
        return await sync_artwork_for_title(db, title)
    items = _reference_artwork_items(title)
    if not items:
        return list_artwork_assets(db, title_id)
    return _replace_tmdb_artwork(db, title_id, items)


async def sync_hierarchy_artwork(db: Session, series: Title) -> None:
    """Populate artwork libraries for a series and its seasons/episodes from core metadata."""
    await auto_sync_artwork_for_title(db, series)
    seasons = db.query(Title).filter(Title.parent_id == series.id).all()
    for season in seasons:
        await auto_sync_artwork_for_title(db, season)
        episodes = db.query(Title).filter(Title.parent_id == season.id).all()
        for episode in episodes:
            await auto_sync_artwork_for_title(db, episode)
