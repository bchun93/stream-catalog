"""Sync TMDB artwork into MediaAsset rows for a title."""

import json

from sqlalchemy.orm import Session

from app.models.media_asset import AssetStatus, AssetType, MediaAsset
from app.models.title import Title
from app.schemas.artwork import ArtworkItem, ArtworkSpecs
from app.services.artwork_metadata import artwork_item_metadata_json
from app.services.poster_resolver import is_usable_poster_url
from app.services.title_service import sync_title_poster_cache
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


def _filter_to_metadata_artwork(
    items: list[ArtworkItem], metadata_json: str | None
) -> list[ArtworkItem]:
    labels_by_filename = _metadata_artwork_labels(metadata_json)
    if not labels_by_filename:
        return items

    selected: dict[str, ArtworkItem] = {}
    for item in items:
        labels = labels_by_filename.get(_uri_basename(item.storage_uri))
        if not labels:
            continue
        if item.storage_uri not in selected:
            selected[item.storage_uri] = _with_artwork_label(item, labels)
    return list(selected.values())


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
    _clear_tmdb_artwork(db, title_id)
    created = _persist_artwork(db, title_id, items)
    db.commit()
    for asset in created:
        db.refresh(asset)
    sync_title_poster_cache(db, title_id)
    return list_artwork_assets(db, title_id)


def _persist_artwork(db: Session, title_id: int, items: list[ArtworkItem]) -> list[MediaAsset]:
    created: list[MediaAsset] = []
    for item in items:
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
        for asset in created:
            db.refresh(asset)
        sync_title_poster_cache(db, title_id)
    elif existing_assets:
        db.commit()

    return list_artwork_assets(db, title_id)


async def sync_artwork_for_title(db: Session, title: Title) -> list[MediaAsset]:
    """Fetch TMDB artwork and save only images referenced by core metadata."""
    if not _is_tmdb_external_id(title.external_id):
        return []
    media_type, tmdb_id = parse_external_id(title.external_id)
    items = await collect_artwork_from_tmdb(media_type, tmdb_id)
    matching_items = _filter_to_metadata_artwork(items, title.metadata_json)
    return _replace_tmdb_artwork(db, title.id, matching_items)
