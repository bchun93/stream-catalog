"""Safe server-side fetch for TMDB artwork URIs."""

import logging

import httpx

from app.services.poster_resolver import is_allowed_tmdb_artwork_uri

logger = logging.getLogger(__name__)

MAX_ARTWORK_BYTES = 25 * 1024 * 1024


def fetch_tmdb_artwork(uri: str) -> tuple[bytes, str]:
    """Download artwork bytes from an allowlisted TMDB image URL."""
    if not is_allowed_tmdb_artwork_uri(uri):
        raise ValueError("Artwork URI is not an allowed TMDB image URL")

    with httpx.Client(timeout=30.0, follow_redirects=False, trust_env=False) as client:
        with client.stream("GET", uri) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > MAX_ARTWORK_BYTES:
                    raise ValueError("Artwork file exceeds size limit")
                chunks.append(chunk)
            media_type = resp.headers.get("content-type") or "image/jpeg"
            return b"".join(chunks), media_type
