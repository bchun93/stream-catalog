import asyncio
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from fastapi import HTTPException

from app.config import settings
from app.models.title import TitleType
from app.schemas.metadata import MetadataSearchResult, TitleMetadataImport

_TMDB_IMAGE = "https://image.tmdb.org/t/p/w185"
# No-proxy opener — avoids Cursor/shell proxy breaking TMDB DNS (Errno 8 / 403).
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _require_api_key() -> str:
    if not settings.tmdb_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "TMDB API key not configured. Set TMDB_API_KEY in backend/.env "
                "(free key at https://www.themoviedb.org/settings/api)"
            ),
        )
    key = settings.tmdb_api_key.strip()
    if key.startswith("your_") or key == "your_tmdb_api_key_here":
        raise HTTPException(
            status_code=503,
            detail="Replace the placeholder TMDB_API_KEY in backend/.env with your real v3 key from themoviedb.org/settings/api",
        )
    return key


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:120] or "title"


def _parse_year(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 4:
        return None
    try:
        return int(text[:4])
    except ValueError:
        return None


def _poster(path: str | None) -> str | None:
    return f"{_TMDB_IMAGE}{path}" if path else None


def _title_type_for_media(media_type: str) -> TitleType:
    return TitleType.SERIES if media_type == "tv" else TitleType.MOVIE


def _fetch_json(path: str, **params) -> dict:
    params["api_key"] = _require_api_key()
    query = urllib.parse.urlencode(params)
    url = f"{settings.tmdb_base_url.rstrip('/')}{path}?{query}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with _NO_PROXY_OPENER.open(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()[:200] if exc.fp else ""
        if exc.code == 401:
            raise HTTPException(
                status_code=503,
                detail="Invalid TMDB API key — check TMDB_API_KEY in backend/.env",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"TMDB error ({exc.code}): {body}",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not reach TMDB ({exc}). "
                "Check internet/DNS, disable VPN, and start the API from Terminal.app: "
                "./scripts/start-backend.sh"
            ),
        ) from exc


async def _get(path: str, **params) -> dict:
    return await asyncio.to_thread(_fetch_json, path, **params)


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
    for media_type in media_types:
        path = "/search/movie" if media_type == "movie" else "/search/tv"
        data = await _get(path, query=query.strip())
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
        roles = member.get("roles") or []
        role = member.get("character") or (
            roles[0].get("character") if roles else None
        )
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
    data = await _get(path, append_to_response=append)

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
    parts = external_id.split(":")
    if len(parts) != 3 or parts[0] != "tmdb":
        raise HTTPException(status_code=400, detail="Invalid external_id format")
    media_type, raw_id = parts[1], parts[2]
    try:
        return media_type, int(raw_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid TMDB id") from exc


async def check_tmdb_connectivity() -> dict:
    try:
        await _get("/search/movie", query="test")
        return {"ok": True, "message": "TMDB reachable"}
    except HTTPException as exc:
        return {"ok": False, "message": exc.detail}
