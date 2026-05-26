import asyncio
import json
import re
from datetime import date

import httpx
from fastapi import HTTPException

from app.config import settings
from app.models.media_asset import AssetType
from app.models.title import TitleType
from app.schemas.artwork import ArtworkItem, ArtworkSpecs
from app.schemas.metadata import (
    EpisodeHierarchyPreview,
    MetadataSearchResult,
    SeasonHierarchyPreview,
    SeriesHierarchyPreview,
    TitleMetadataImport,
)


class TmdbServiceError(Exception):
    """Raised from sync TMDB helpers; converted to HTTPException in async layer."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


_TMDB_IMAGE = "https://image.tmdb.org/t/p/w185"
TMDB_SOURCE_NOTE = "source:tmdb"
# English (US) artwork — TMDB image language filter + API locale.
_TMDB_LANGUAGE = "en-US"
_TMDB_IMAGE_LANGUAGES = "en,null"

_IMAGE_SIZE = {
    AssetType.POSTER: "w500",
    AssetType.BACKDROP: "w780",
    AssetType.LOGO: "w500",
    AssetType.STILL: "w780",
    AssetType.CAST_PHOTO: "w185",
    AssetType.SEASON_POSTER: "w500",
}

_IMAGE_LIMITS = {
    AssetType.POSTER: 24,
    AssetType.BACKDROP: 16,
    AssetType.LOGO: 16,
    AssetType.STILL: 16,
    AssetType.CAST_PHOTO: 24,
    AssetType.SEASON_POSTER: 40,
}

_IMAGES_KEY_TO_TYPE = {
    "posters": AssetType.POSTER,
    "backdrops": AssetType.BACKDROP,
    "logos": AssetType.LOGO,
    "stills": AssetType.STILL,
}
# trust_env=False — ignore HTTP_PROXY / ALL_PROXY so TMDB calls work in dev shells.
_TMDb_HTTP = httpx.Client(timeout=20.0, trust_env=False)

_REQUIREMENTS_FIELDS: tuple[str, ...] = (
    "content_type",
    "movie_ref",
    "series_ref",
    "season_ref",
    "reference_id",
    "name",
    "synopsis",
    "short_synopsis",
    "season_count",
    "season_number",
    "episode_count",
    "episode_no",
    "copyright_line",
    "rating",
    "advisory",
    "release_date",
    "initial_release_year",
    "latest_release_year",
    "runtime",
    "studio",
    "genre",
    "language",
    "origin",
    "actors",
    "directors",
    "writers",
    "creators",
    "producers",
    "h_poster",
    "still_frame",
    "v_poster",
    "logo",
    "hero_image",
    "hero_image_vertical",
    "box_art",
    "source_file_name",
    "ad_dv",
    "hd_sd",
    "surround",
    "cc",
    "cc_language",
    "forced_narrative_cc",
    "forced_narrative_cc_language",
    "photosensitivity",
    "dubbing",
    "dubbing_language",
    "dub_cards",
    "skip_intro_start",
    "skip_intro_end",
    "skip_recap_start",
    "skip_recap_end",
    "skip_creds_start",
    "ad_breaks",
    "tags",
    "playback_start_date",
    "playback_end_date",
)


def _require_api_key() -> str:
    if not settings.tmdb_api_key:
        raise TmdbServiceError(
            503,
            "TMDB API key not configured. Set TMDB_API_KEY on Render (Environment).",
        )
    key = settings.tmdb_api_key.strip()
    if key.startswith("your_") or key == "your_tmdb_api_key_here":
        raise TmdbServiceError(
            503,
            "Replace the placeholder TMDB_API_KEY with your real v3 key from themoviedb.org/settings/api",
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
    return _image_url(path, "w185")


def _image_url(path: str | None, size: str = "w500") -> str | None:
    if not path:
        return None
    return f"https://image.tmdb.org/t/p/{size}{path}"


def _resolution(width: int | None, height: int | None) -> str | None:
    if width and height:
        return f"{width}×{height}"
    return None


def _aspect_ratio_label(ratio: float | None) -> str | None:
    if ratio is None:
        return None
    pairs = [
        (0.667, "2:3"),
        (0.75, "3:4"),
        (1.0, "1:1"),
        (1.778, "16:9"),
        (2.333, "21:9"),
    ]
    for target, label in pairs:
        if abs(ratio - target) < 0.06:
            return label
    return f"{ratio:.2f}:1"


def _specs_from_image(image: dict, *, label: str | None = None) -> ArtworkSpecs:
    width = image.get("width")
    height = image.get("height")
    ar = image.get("aspect_ratio")
    lang = image.get("iso_639_1")
    return ArtworkSpecs(
        width=width,
        height=height,
        aspect_ratio=ar,
        aspect_ratio_label=_aspect_ratio_label(ar),
        resolution=_resolution(width, height),
        language=lang,
        country=image.get("iso_3166_1"),
        vote_average=image.get("vote_average"),
        vote_count=image.get("vote_count"),
        label=label,
    )


def _artwork_filename(asset_type: AssetType, file_path: str, *parts: str) -> str:
    base = (file_path or "image").strip("/").replace("/", "_")
    suffix = "_".join(p for p in parts if p)
    name = asset_type.value
    raw = f"{name}_{suffix}_{base}" if suffix else f"{name}_{base}"
    return raw[:255]


def _is_english_or_neutral(lang: str | None) -> bool:
    return lang in (None, "", "en")


def _rank_images_english_first(images: list[dict]) -> list[dict]:
    """Prefer English and language-neutral images, then by TMDB vote."""

    def sort_key(img: dict) -> tuple[int, float]:
        lang = img.get("iso_639_1")
        tier = 0 if _is_english_or_neutral(lang) else 1
        return (tier, -(img.get("vote_average") or 0))

    return sorted(images, key=sort_key)


def _tmdb_image_params(**extra: str) -> dict[str, str]:
    return {
        "language": _TMDB_LANGUAGE,
        "include_image_language": _TMDB_IMAGE_LANGUAGES,
        **extra,
    }


def _items_from_images(
    images: list[dict],
    asset_type: AssetType,
    *,
    note_prefix: str | None = None,
) -> list[ArtworkItem]:
    limit = _IMAGE_LIMITS[asset_type]
    size = _IMAGE_SIZE[asset_type]
    ranked = _rank_images_english_first(images)
    english = [i for i in ranked if _is_english_or_neutral(i.get("iso_639_1"))]
    fallback = [i for i in ranked if not _is_english_or_neutral(i.get("iso_639_1"))]
    pool = english + fallback
    items: list[ArtworkItem] = []
    seen: set[str] = set()
    for image in pool[:limit]:
        path = image.get("file_path")
        url = _image_url(path, size)
        if not url or url in seen:
            continue
        seen.add(url)
        lang = image.get("iso_639_1")
        specs = _specs_from_image(image, label=note_prefix)
        note = f"{TMDB_SOURCE_NOTE}; locale:en-US"
        if note_prefix:
            note = f"{note}; {note_prefix}"
        if lang and lang != "en":
            note = f"{note}; lang:{lang}"
        items.append(
            ArtworkItem(
                asset_type=asset_type,
                storage_uri=url,
                filename=_artwork_filename(asset_type, path, lang or "xx"),
                mime_type="image/jpeg",
                language=lang,
                resolution=specs.resolution,
                notes=note,
                specs=specs,
            )
        )
    return items


def _title_type_for_media(media_type: str) -> TitleType:
    return TitleType.SERIES if media_type == "tv" else TitleType.MOVIE


def _fetch_json(path: str, **params) -> dict:
    params["api_key"] = _require_api_key()
    url = f"{settings.tmdb_base_url.rstrip('/')}{path}"
    try:
        resp = _TMDb_HTTP.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "")[:200]
        if exc.response.status_code == 401:
            raise TmdbServiceError(
                503,
                "Invalid TMDB API key — check TMDB_API_KEY on Render.",
            ) from exc
        raise TmdbServiceError(
            502,
            f"TMDB error ({exc.response.status_code}): {body}",
        ) from exc
    except httpx.RequestError as exc:
        raise TmdbServiceError(
            503,
            f"Could not reach TMDB ({exc}). Check TMDB_API_KEY and Render outbound network.",
        ) from exc


async def _get(path: str, **params) -> dict:
    try:
        return await asyncio.to_thread(_fetch_json, path, **params)
    except TmdbServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


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
            tmdb_id = item.get("id")
            if tmdb_id is None:
                continue
            date_field = item.get("release_date") or item.get("first_air_date")
            year = _parse_year(date_field)
            overview = item.get("overview")
            if overview is not None and not isinstance(overview, str):
                overview = str(overview)
            results.append(
                MetadataSearchResult(
                    external_id=f"tmdb:{media_type}:{tmdb_id}",
                    media_type=media_type,
                    title_type=_title_type_for_media(media_type),
                    name=str(item.get("title") or item.get("name") or "Unknown"),
                    release_year=year,
                    overview=overview,
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


def _crew_names(credits: dict, *jobs: str, limit: int = 12) -> str | None:
    crew = credits.get("crew") or []
    names: list[str] = []
    wanted = set(jobs)
    for member in crew:
        if member.get("job") not in wanted:
            continue
        name = member.get("name")
        if not name or name in names:
            continue
        names.append(name)
        if len(names) >= limit:
            break
    return "\n".join(names) if names else None


def _cast_names(credits: dict, limit: int = 20) -> str | None:
    cast = credits.get("cast") or []
    names: list[str] = []
    for member in cast:
        name = member.get("name")
        if not name or name in names:
            continue
        names.append(name)
        if len(names) >= limit:
            break
    return "\n".join(names) if names else None


def _to_mmddyyyy(value: str | None) -> str | None:
    if not value:
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None
    return d.strftime("%m/%d/%Y")


def _basename(path: str | None) -> str | None:
    if not path:
        return None
    return path.strip().split("/")[-1] or None


def _requirements_template() -> dict[str, str | None]:
    return {field: None for field in _REQUIREMENTS_FIELDS}


def _season_slug(series_name: str, season_number: int) -> str:
    suffix = "specials" if season_number == 0 else f"season-{season_number}"
    return f"{_slugify(series_name)}-{suffix}"[:120]


def _episode_slug(series_name: str, season_number: int, episode_number: int, name: str) -> str:
    season_part = "s00" if season_number == 0 else f"s{season_number:02d}"
    episode_part = f"e{episode_number:02d}"
    title_part = _slugify(name)
    return f"{_slugify(series_name)}-{season_part}{episode_part}-{title_part}"[:120]


def _tmdb_core_metadata(
    *,
    data: dict,
    media_type: str,
    name: str,
    synopsis: str | None,
    short_synopsis: str | None,
    release_date_value: str | None,
    release_year: int | None,
    rating: str | None,
    runtime: int | None,
    studio: str | None,
    genres: str | None,
    credits: dict,
) -> dict[str, str | None]:
    values = _requirements_template()
    values["content_type"] = "series" if media_type == "tv" else "movie"
    values["name"] = name
    values["synopsis"] = synopsis
    values["short_synopsis"] = short_synopsis
    values["rating"] = rating
    values["release_date"] = _to_mmddyyyy(release_date_value)
    values["runtime"] = str(runtime) if runtime is not None else None
    values["studio"] = studio.replace(", ", "\n") if studio else None
    values["genre"] = genres.replace(", ", "\n") if genres else None
    values["language"] = (data.get("original_language") or "").strip().lower() or None

    countries = data.get("production_countries") or []
    country_codes = [c.get("iso_3166_1") for c in countries if c.get("iso_3166_1")]
    if country_codes:
        values["origin"] = "\n".join(country_codes[:10])

    values["actors"] = _cast_names(credits)
    values["directors"] = _crew_names(credits, "Director")
    values["writers"] = _crew_names(credits, "Writer", "Screenplay")
    values["producers"] = _crew_names(credits, "Producer", "Executive Producer")

    created_by = data.get("created_by") or []
    creators = [p.get("name") for p in created_by if p.get("name")]
    if creators:
        values["creators"] = "\n".join(creators[:10])

    if media_type == "tv":
        season_count = data.get("number_of_seasons")
        if season_count is not None:
            values["season_count"] = str(season_count)
        first = _parse_year(data.get("first_air_date"))
        latest = _parse_year(data.get("last_air_date")) or release_year
        if first is not None:
            values["initial_release_year"] = str(first)
        if latest is not None:
            values["latest_release_year"] = str(latest)

    poster_path = data.get("poster_path")
    backdrop_path = data.get("backdrop_path")
    values["v_poster"] = _basename(poster_path)
    values["h_poster"] = _basename(backdrop_path)
    values["hero_image"] = _basename(backdrop_path)
    values["still_frame"] = _basename(backdrop_path)
    values["box_art"] = _basename(poster_path)

    if media_type == "movie":
        values["movie_ref"] = f"tmdb_movie_{data.get('id')}"
    else:
        values["series_ref"] = f"tmdb_tv_{data.get('id')}"

    values["reference_id"] = f"tmdb_{media_type}_{data.get('id')}"

    keyword_rows = []
    keywords = data.get("keywords") or {}
    keyword_list = keywords.get("keywords") if media_type == "movie" else keywords.get("results")
    if isinstance(keyword_list, list):
        for kw in keyword_list:
            name = kw.get("name")
            if name:
                keyword_rows.append(str(name))
            if len(keyword_rows) >= 12:
                break
    values["tags"] = "\n".join(keyword_rows) if keyword_rows else None

    return values


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


async def collect_artwork_from_tmdb(
    media_type: str, tmdb_id: int
) -> list[ArtworkItem]:
    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=400, detail="media_type must be movie or tv")

    items: list[ArtworkItem] = []
    images_data = await _get(
        f"/{media_type}/{tmdb_id}/images",
        **_tmdb_image_params(),
    )
    for key, asset_type in _IMAGES_KEY_TO_TYPE.items():
        if key == "stills" and media_type != "tv":
            continue
        batch = images_data.get(key) or []
        if batch:
            items.extend(_items_from_images(batch, asset_type))

    credits_data = await _get(
        f"/{media_type}/{tmdb_id}",
        append_to_response="credits",
        language=_TMDB_LANGUAGE,
    )
    cast = credits_data.get("credits", {}).get("cast") or []
    cast_items: list[ArtworkItem] = []
    seen_cast: set[str] = set()
    for member in cast:
        path = member.get("profile_path")
        url = _image_url(path, _IMAGE_SIZE[AssetType.CAST_PHOTO])
        if not url or url in seen_cast:
            continue
        seen_cast.add(url)
        name = member.get("name") or "Unknown"
        character = member.get("character")
        note = f"{TMDB_SOURCE_NOTE}; {name}"
        if character:
            note = f"{note} as {character}"
        cast_label = f"{name} as {character}" if character else name
        cast_specs = ArtworkSpecs(
            width=member.get("width"),
            height=member.get("height"),
            resolution=_resolution(member.get("width"), member.get("height")),
            label=cast_label,
        )
        cast_items.append(
            ArtworkItem(
                asset_type=AssetType.CAST_PHOTO,
                storage_uri=url,
                filename=_artwork_filename(AssetType.CAST_PHOTO, path, name.replace(" ", "_")),
                mime_type="image/jpeg",
                resolution=cast_specs.resolution,
                notes=note,
                specs=cast_specs,
            )
        )
        if len(cast_items) >= _IMAGE_LIMITS[AssetType.CAST_PHOTO]:
            break
    items.extend(cast_items)

    if media_type == "tv":
        detail = await _get(f"/tv/{tmdb_id}", language=_TMDB_LANGUAGE)
        for season in detail.get("seasons") or []:
            if season.get("season_number", 0) == 0:
                continue
            path = season.get("poster_path")
            url = _image_url(path, _IMAGE_SIZE[AssetType.SEASON_POSTER])
            if not url:
                continue
            season_num = season.get("season_number")
            season_specs = ArtworkSpecs(
                label=f"Season {season_num}",
                language="en",
            )
            items.append(
                ArtworkItem(
                    asset_type=AssetType.SEASON_POSTER,
                    storage_uri=url,
                    filename=_artwork_filename(
                        AssetType.SEASON_POSTER, path, f"s{season_num}"
                    ),
                    mime_type="image/jpeg",
                    notes=f"{TMDB_SOURCE_NOTE}; season:{season_num}",
                    specs=season_specs,
                )
            )
            if len([i for i in items if i.asset_type == AssetType.SEASON_POSTER]) >= _IMAGE_LIMITS[AssetType.SEASON_POSTER]:
                break

    return items


async def fetch_metadata(
    media_type: str, tmdb_id: int
) -> TitleMetadataImport:
    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=400, detail="media_type must be movie or tv")

    append = (
        "credits,release_dates,keywords"
        if media_type == "movie"
        else "credits,content_ratings,keywords"
    )
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

    external_id = f"tmdb:{media_type}:{tmdb_id}"

    return TitleMetadataImport(
        external_id=external_id,
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
        core_metadata=_tmdb_core_metadata(
            data=data,
            media_type=media_type,
            name=name,
            synopsis=data.get("overview"),
            short_synopsis=data.get("tagline"),
            release_date_value=release_date_value,
            release_year=release_year,
            rating=certification,
            runtime=runtime,
            studio=_studios(data, media_type),
            genres=genres or None,
            credits=credits,
        ),
        artwork=[],
    )


def _season_core_metadata(
    *,
    series_id: int,
    season_data: dict,
    season_number: int,
    episode_count: int,
) -> dict[str, str | None]:
    values = _requirements_template()
    values["content_type"] = "season"
    values["name"] = str(season_data.get("name") or f"Season {season_number}")
    values["synopsis"] = season_data.get("overview")
    values["release_date"] = _to_mmddyyyy(season_data.get("air_date"))
    values["season_number"] = str(season_number)
    values["episode_count"] = str(episode_count)
    year = _parse_year(season_data.get("air_date"))
    if year is not None:
        values["initial_release_year"] = str(year)
        values["latest_release_year"] = str(year)
    values["series_ref"] = f"tmdb_tv_{series_id}"
    values["season_ref"] = f"tmdb_tv_{series_id}_season_{season_number}"
    values["reference_id"] = f"tmdb_tv_{series_id}_season_{season_number}"
    values["v_poster"] = _basename(season_data.get("poster_path"))
    values["box_art"] = _basename(season_data.get("poster_path"))
    return values


def _episode_core_metadata(
    *,
    series_id: int,
    season_number: int,
    episode_data: dict,
) -> dict[str, str | None]:
    values = _requirements_template()
    episode_number = int(episode_data.get("episode_number") or 0)
    runtime = episode_data.get("runtime")
    values["content_type"] = "episode"
    values["name"] = str(episode_data.get("name") or f"Episode {episode_number}")
    values["synopsis"] = episode_data.get("overview")
    values["release_date"] = _to_mmddyyyy(episode_data.get("air_date"))
    values["season_number"] = str(season_number)
    values["episode_no"] = str(episode_number)
    values["runtime"] = str(runtime) if runtime is not None else None
    year = _parse_year(episode_data.get("air_date"))
    if year is not None:
        values["initial_release_year"] = str(year)
        values["latest_release_year"] = str(year)
    values["series_ref"] = f"tmdb_tv_{series_id}"
    values["season_ref"] = f"tmdb_tv_{series_id}_season_{season_number}"
    values["reference_id"] = (
        f"tmdb_tv_{series_id}_season_{season_number}_episode_{episode_number}"
    )
    values["still_frame"] = _basename(episode_data.get("still_path"))
    values["hero_image"] = _basename(episode_data.get("still_path"))
    return values


async def fetch_series_hierarchy_preview(tmdb_id: int) -> SeriesHierarchyPreview:
    series_meta = await fetch_metadata("tv", tmdb_id)
    series_data = await _get(
        f"/tv/{tmdb_id}",
        append_to_response="credits,content_ratings,keywords",
        language=_TMDB_LANGUAGE,
    )
    series_name = series_data.get("name") or series_meta.name
    seasons: list[SeasonHierarchyPreview] = []

    for season_stub in sorted(
        series_data.get("seasons") or [],
        key=lambda s: int(s.get("season_number") or 0),
    ):
        season_number = int(season_stub.get("season_number") or 0)
        season_data = await _get(
            f"/tv/{tmdb_id}/season/{season_number}",
            language=_TMDB_LANGUAGE,
        )
        season_name = (
            "Specials"
            if season_number == 0
            else str(season_data.get("name") or f"Season {season_number}")
        )
        episodes: list[EpisodeHierarchyPreview] = []
        for episode in sorted(
            season_data.get("episodes") or [],
            key=lambda e: int(e.get("episode_number") or 0),
        ):
            episode_number = int(episode.get("episode_number") or 0)
            episode_name = str(episode.get("name") or f"Episode {episode_number}")
            external_id = (
                f"tmdb:tv:{tmdb_id}:season:{season_number}:episode:{episode_number}"
            )
            episodes.append(
                EpisodeHierarchyPreview(
                    external_id=external_id,
                    name=episode_name,
                    slug=_episode_slug(
                        series_name,
                        season_number,
                        episode_number,
                        episode_name,
                    ),
                    season_number=season_number,
                    episode_number=episode_number,
                    synopsis=episode.get("overview"),
                    release_date=episode.get("air_date"),
                    runtime_minutes=episode.get("runtime"),
                    still_url=_image_url(episode.get("still_path"), "w300"),
                    core_metadata=_episode_core_metadata(
                        series_id=tmdb_id,
                        season_number=season_number,
                        episode_data=episode,
                    ),
                )
            )

        episode_count = len(episodes)
        seasons.append(
            SeasonHierarchyPreview(
                external_id=f"tmdb:tv:{tmdb_id}:season:{season_number}",
                name=season_name,
                slug=_season_slug(series_name, season_number),
                season_number=season_number,
                synopsis=season_data.get("overview"),
                release_date=season_data.get("air_date"),
                poster_url=_poster(season_data.get("poster_path")),
                episode_count=episode_count,
                core_metadata=_season_core_metadata(
                    series_id=tmdb_id,
                    season_data=season_data,
                    season_number=season_number,
                    episode_count=episode_count,
                ),
                episodes=episodes,
            )
        )

    return SeriesHierarchyPreview(
        external_id=series_meta.external_id,
        name=series_meta.name,
        slug=series_meta.slug or _slugify(series_meta.name),
        synopsis=series_meta.synopsis,
        short_description=series_meta.short_description,
        release_date=series_meta.release_date,
        release_year=series_meta.release_year,
        rating=series_meta.rating,
        genres=series_meta.genres,
        runtime_minutes=series_meta.runtime_minutes,
        studio=series_meta.studio,
        cast=series_meta.cast,
        crew=series_meta.crew,
        poster_url=series_meta.poster_url,
        core_metadata=series_meta.core_metadata,
        seasons=seasons,
        season_count=len(seasons),
        episode_count=sum(season.episode_count for season in seasons),
    )


def parse_external_id(external_id: str) -> tuple[str, int]:
    from urllib.parse import unquote  # stdlib — external_id decoding only

    normalized = unquote(external_id).strip().rstrip("/")
    if normalized.endswith("/artwork"):
        normalized = normalized[: -len("/artwork")]
    parts = normalized.split(":")
    if len(parts) != 3 or parts[0] != "tmdb":
        raise HTTPException(status_code=400, detail="Invalid external_id format")
    media_type, raw_id = parts[1], parts[2]
    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=400, detail="media_type must be movie or tv")
    try:
        return media_type, int(raw_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid TMDB id") from exc


async def check_tmdb_connectivity() -> dict:
    try:
        await _get("/search/movie", query="test")
        return {"ok": True, "message": "TMDB reachable"}
    except HTTPException as exc:
        return {"ok": False, "message": str(exc.detail)}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
