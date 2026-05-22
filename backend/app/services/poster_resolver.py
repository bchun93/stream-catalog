"""Resolve a display poster URL for titles — skips invalid/broken image links."""

import re

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

_TMDB_IMAGE_RE = re.compile(
    r"^https://image\.tmdb\.org/t/p/[\w]+/[\w.-]+\.(?:jpg|jpeg|png|webp)$",
    re.IGNORECASE,
)

_BLOCKED_PATH_FRAGMENTS = ("/test.", "/test.jpg", "/placeholder.", "/null.")


def is_usable_poster_url(url: str | None) -> bool:
    if not url or not url.strip():
        return False
    normalized = url.strip()
    lower = normalized.lower()
    if any(fragment in lower for fragment in _BLOCKED_PATH_FRAGMENTS):
        return False
    if "image.tmdb.org" in lower:
        return bool(_TMDB_IMAGE_RE.match(normalized))
    return normalized.startswith(("http://", "https://"))


def pick_best_poster_uri(assets: list[MediaAsset]) -> str | None:
    """Choose the best poster-like asset; ignore invalid TMDB paths."""
    candidates = [
        a
        for a in assets
        if a.asset_type in _POSTER_TYPES and is_usable_poster_url(a.storage_uri)
    ]
    if not candidates:
        return None

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
