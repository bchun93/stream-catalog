import re
from datetime import date

import httpx
from fastapi import HTTPException

from app.config import settings
from app.models.title import TitleType
from app.schemas.metadata import MetadataSearchResult, TitleMetadataImport

_TMDB_IMAGE = "https://image.tmdb.org/t/p/w185"


def _require_api_key() -> str:
    if not settings.tmdb_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "TMDB API key not configured. Set TMDB_API_KEY in backend/.env "
                "(free key at https://www.themoviedb.org/settings/api)"
            ),
        )
    return settings.tmdb_api_key


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:120] or "title"


def _parse_year(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def _poster(path: str | None) -> str | None:
    return f"{_TMDB_IMAGE}{path}" if path else None


def _title_type_for_media(media_type: str) -> TitleType:
    return TitleType.SERIES if media_type == "tv" else TitleType.MOVIE


async def _get(client: httpx.AsyncClient, path: str, **params) -> dict:
    params["api_key"] = _require_api_key()
    res = await client.get(f"{settings.tmdb_base_url}{path}", params=params)
    if res.status_code == 401:
        raise HTTPException(status_code=503, detail="Invalid TMDB API key")
    res.raise_for_status()
    return res.json()


async def search_metadata(
    query: str, title_type: TitleType | None = None
) -> list[MetadataSearchResult]:
    if not query.strip():
        return []

    media_types: list[str] = []
    if title_type in (None, TitleType.MOVIE):
        media_types.append("movie")
    if title_type in (None, TitleType.SERIES):
        media_types.append("tv")

    results: list[MetadataSearchResult] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for media_type in media_types:
            path = "/search/movie" if media_type == "movie" else "/search/tv"
            data = await _get(client, path, query=query.strip())
            for item in data.get("results", [])[:8]:
                date_field = item.get("release_date") or item.get("first_air_date")
                year = _parse_year(date_field)
                tmdb_id = item["id"]
                results.append(
                    MetadataSearchResult(
                        external_id=f"tmdb:{media_type}:{tmdb_id}",
                        media_type=media_type,
                        title_type=_title_type_for_media(media_type),
                        name=item.get("title") or item.get("name") or "Unknown",
                        release_year=year,
                        overview=item.get("overview"),
                        poster_url=_poster(item.get("poster_path")),
                    )
                )
    return results[:16]


def _format_cast(credits: dict, limit: int = 12) -> str | None:
    cast = credits.get("cast") or []
    if not cast:
        return None
    parts = []
    for member in cast[:limit]:
        name = member.get("name")
        role = member.get("character") or member.get("roles", [{}])[0].get("character")
        if name and role:
            parts.append(f"{name} ({role})")
        elif name:
            parts.append(name)
    return "; ".join(parts) if parts else None


def _format_crew(credits: dict) -> str | None:
    crew = credits.get("crew") or []
    if not crew:
        return None
    roles = {
        "Director": [],
        "Writer": [],
        "Screenplay": [],
        "Producer": [],
        "Executive Producer": [],
    }
    for member in crew:
        job = member.get("job")
        name = member.get("name")
        if job in roles and name and name not in roles[job]:
            roles[job].append(name)
    segments = []
    for job, names in roles.items():
        if names:
            segments.append(f"{job}: {', '.join(names[:4])}")
    return "; ".join(segments) if segments else None


def _us_certification(movie_data: dict, media_type: str) -> str | None:
    if media_type == "movie":
        for country in movie_data.get("release_dates", {}).get("results", []):
            if country.get("iso_3166_1") == "US":
                for release in country.get("release_dates", []):
                    cert = release.get("certification")
                    if cert:
                        return cert
    else:
        for rating in movie_data.get("content_ratings", {}).get("results", []):
            if rating.get("iso_3166_1") == "US":
                return rating.get("rating")
    return None


def _studios(data: dict, media_type: str) -> str | None:
    companies = data.get("production_companies") or []
    names = [c.get("name") for c in companies if c.get("name")]
    if names:
        return ", ".join(names[:5])
    networks = data.get("networks") or []
    network_names = [n.get("name") for n in networks if n.get("name")]
    return ", ".join(network_names[:3]) if network_names else None


async def fetch_metadata(
    media_type: str, tmdb_id: int
) -> TitleMetadataImport:
    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=400, detail="media_type must be movie or tv")

    append = "credits,release_dates" if media_type == "movie" else "credits,content_ratings"
    path = f"/{media_type}/{tmdb_id}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        data = await _get(client, path, append_to_response=append)

    name = data.get("title") or data.get("name") or "Unknown"
    date_str = data.get("release_date") or data.get("first_air_date")
    release_year = _parse_year(date_str)
    genres = ", ".join(g["name"] for g in data.get("genres", []) if g.get("name"))

    runtime = data.get("runtime")
    if runtime is None and data.get("episode_run_time"):
        runtime = data["episode_run_time"][0] if data["episode_run_time"] else None

    credits = data.get("credits") or {}
    certification = _us_certification(data, media_type)

    release_date_value = None
    if date_str:
        try:
            release_date_value = date.fromisoformat(date_str).isoformat()
        except ValueError:
            release_date_value = date_str

    return TitleMetadataImport(
        external_id=f"tmdb:{media_type}:{tmdb_id}",
        media_type=media_type,
        title_type=_title_type_for_media(media_type),
        name=name,
        slug=_slugify(name),
        synopsis=data.get("overview"),
        short_description=data.get("tagline"),
        release_date=release_date_value,
        release_year=release_year,
        rating=certification,
        genres=genres or None,
        runtime_minutes=runtime,
        studio=_studios(data, media_type),
        licensor=None,
        cast=_format_cast(credits),
        crew=_format_crew(credits),
        poster_url=_poster(data.get("poster_path")),
    )


def parse_external_id(external_id: str) -> tuple[str, int]:
    """Parse tmdb:movie:550 -> (movie, 550)"""
    parts = external_id.split(":")
    if len(parts) != 3 or parts[0] != "tmdb":
        raise HTTPException(status_code=400, detail="Invalid external_id format")
    media_type, raw_id = parts[1], parts[2]
    try:
        return media_type, int(raw_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid TMDB id") from exc
