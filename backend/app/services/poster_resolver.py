"""Resolve a display poster URL for titles — skips invalid/broken image links."""

import re
import json

from app.models.media_asset import AssetType, MediaAsset

_POSTER_TYPES = (
    AssetType.POSTER,
    AssetType.SEASON_POSTER,
    AssetType.THUMBNAIL,
)

_TYPE_PRIORITY = {
    AssetType.POSTER: 0,
    AssetType.SEASON_POSTER: 1,
    AssetType.THUMBNAIL: 2,
}

_NON_POSTER_LABELS = {
    "hero image",
    "horizontal poster",
    "still frame",
    "logo",
    "cast photo",
}

_PREFERRED_POSTER_LABELS = (
    "vertical poster",
    "box art",
)

_CAST_URI_MARKERS = ("/w185/", "/w154/", "/w45/")

_TMDB_IMAGE_RE = re.compile(
    r"^https://image\.tmdb\.org/t/p/[\w]+/[\w.-]+\.(?:jpg|jpeg|png|webp)$",
    re.IGNORECASE,
)

_BLOCKED_PATH_FRAGMENTS = ("/test.", "/test.jpg", "/placeholder.", "/null.")


def is_allowed_tmdb_artwork_uri(url: str | None) -> bool:
    """Strict allowlist for artwork storage and server-side fetch (TMDB CDN only)."""
    if not url or not url.strip():
        return False
    normalized = url.strip()
    lower = normalized.lower()
    if any(fragment in lower for fragment in _BLOCKED_PATH_FRAGMENTS):
        return False
    return bool(_TMDB_IMAGE_RE.match(normalized))


def is_usable_poster_url(url: str | None) -> bool:
    return is_allowed_tmdb_artwork_uri(url)


def _artwork_label(asset: MediaAsset) -> str | None:
    if asset.metadata_json:
        try:
            data = json.loads(asset.metadata_json)
            specs = data.get("specs") if isinstance(data, dict) else None
            label = specs.get("label") if isinstance(specs, dict) else None
            if isinstance(label, str) and label.strip():
                return label.strip().lower()
        except (json.JSONDecodeError, AttributeError):
            pass
    if asset.notes:
        for part in asset.notes.split(";"):
            text = part.strip().lower()
            if text and not text.startswith(("source:", "locale:", "lang:")):
                return text
    return None


def _is_cast_asset(asset: MediaAsset) -> bool:
    if asset.asset_type == AssetType.CAST_PHOTO:
        return True
    label = _artwork_label(asset)
    if label and " as " in label:
        return True
    uri = (asset.storage_uri or "").lower()
    return any(marker in uri for marker in _CAST_URI_MARKERS)


def _is_poster_candidate(asset: MediaAsset) -> bool:
    if _is_cast_asset(asset):
        return False
    if asset.asset_type not in _POSTER_TYPES:
        return False
    label = _artwork_label(asset)
    return label not in _NON_POSTER_LABELS


def pick_best_poster_uri(assets: list[MediaAsset]) -> str | None:
    """Choose the best poster-like asset; ignore invalid TMDB paths."""
    candidates = [
        a
        for a in assets
        if _is_poster_candidate(a) and is_usable_poster_url(a.storage_uri)
    ]
    if not candidates:
        return None

    for preferred in _PREFERRED_POSTER_LABELS:
        for asset in candidates:
            label = _artwork_label(asset)
            if label == preferred:
                return asset.storage_uri

    def sort_key(asset: MediaAsset) -> tuple[int, float]:
        priority = _TYPE_PRIORITY.get(asset.asset_type, 9)
        updated = asset.updated_at.timestamp() if asset.updated_at else 0.0
        return (priority, -updated)

    candidates.sort(key=sort_key)
    return candidates[0].storage_uri


def resolve_poster_url(
    *,
    cached_poster_url: str | None,
    assets: list[MediaAsset],
) -> str | None:
    """Catalog poster assets win; fall back to metadata-cached poster on the title."""
    picked = pick_best_poster_uri(assets)
    if picked:
        return picked
    if is_usable_poster_url(cached_poster_url):
        return cached_poster_url
    return None
