import logging
import json
import secrets
from collections import defaultdict
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.media_asset import AssetType, MediaAsset
from app.models.title import Title, TitleStatus, TitleType
from app.schemas.metadata import SeriesHierarchyApplyResult, SeriesHierarchyPreview
from app.schemas.title import TitleCreate, TitleRead, TitleUpdate
from app.services.poster_resolver import pick_best_poster_uri, resolve_poster_url

logger = logging.getLogger(__name__)

_POSTER_TYPES = (
    AssetType.POSTER,
    AssetType.SEASON_POSTER,
    AssetType.THUMBNAIL,
)

_INTERNAL_ID_PREFIX = "SC"


def _new_internal_id() -> str:
    return f"{_INTERNAL_ID_PREFIX}-{secrets.token_hex(6).upper()}"


def _generate_unique_internal_id(db: Session) -> str:
    while True:
        candidate = _new_internal_id()
        if not db.query(Title).filter(Title.internal_id == candidate).first():
            return candidate


def _ensure_internal_id(db: Session, title: Title) -> None:
    if not title.internal_id:
        title.internal_id = _generate_unique_internal_id(db)


def _ensure_internal_ids(db: Session, titles: list[Title]) -> bool:
    changed = False
    for title in titles:
        if not title.internal_id:
            title.internal_id = _generate_unique_internal_id(db)
            changed = True
    return changed


def list_titles(
    db: Session,
    *,
    q: str | None = None,
    title_type: TitleType | None = None,
    parent_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Title]:
    query = db.query(Title)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                Title.name.ilike(pattern),
                Title.slug.ilike(pattern),
                Title.internal_id.ilike(pattern),
            )
        )
    if title_type:
        query = query.filter(Title.title_type == title_type)
    if parent_id is not None:
        query = query.filter(Title.parent_id == parent_id)
    return query.order_by(Title.updated_at.desc()).offset(skip).limit(limit).all()


def _poster_assets_by_title(
    db: Session, title_ids: list[int]
) -> dict[int, list[MediaAsset]]:
    if not title_ids:
        return {}
    assets = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.title_id.in_(title_ids),
            MediaAsset.asset_type.in_(_POSTER_TYPES),
        )
        .order_by(MediaAsset.updated_at.desc())
        .all()
    )
    grouped: dict[int, list[MediaAsset]] = defaultdict(list)
    for asset in assets:
        grouped[asset.title_id].append(asset)
    return grouped


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _merge_metadata_json(existing_raw: str | None, incoming: dict[str, str | None]) -> str | None:
    if not incoming:
        return existing_raw
    existing: dict[str, str | None] = {}
    if existing_raw:
        try:
            parsed = json.loads(existing_raw)
            if isinstance(parsed, dict):
                existing = {
                    str(key): value if isinstance(value, str) else None
                    for key, value in parsed.items()
                }
        except json.JSONDecodeError:
            existing = {}
    for key, value in incoming.items():
        if existing.get(key):
            continue
        existing[key] = value
    if not any(value for value in existing.values()):
        return None
    return json.dumps(existing)


def _find_title_for_hierarchy(
    db: Session,
    *,
    external_id: str,
    slug: str,
    parent_id: int | None,
) -> Title | None:
    title = db.query(Title).filter(Title.external_id == external_id).first()
    if title:
        return title
    return (
        db.query(Title)
        .filter(Title.slug == slug, Title.parent_id == parent_id)
        .first()
    )


def _unique_slug(db: Session, slug: str, title_id: int | None = None) -> str:
    base = slug[:120] or "title"
    candidate = base
    counter = 2
    while True:
        query = db.query(Title).filter(Title.slug == candidate)
        if title_id is not None:
            query = query.filter(Title.id != title_id)
        if not query.first():
            return candidate
        suffix = f"-{counter}"
        candidate = f"{base[: 120 - len(suffix)]}{suffix}"
        counter += 1


def _set_if_blank(title: Title, field: str, value) -> None:
    if value is None:
        return
    current = getattr(title, field)
    if current in (None, ""):
        setattr(title, field, value)


def _season_display_name(series_name: str, season_number: int | None) -> str:
    season_label = "Specials" if season_number == 0 else f"Season {season_number or 1}"
    return f"{series_name}: {season_label}"


def _episode_title_name(current_name: str) -> str:
    text = (current_name or "").strip()
    if ": Episode " not in text:
        return text
    tail = text.split(": Episode ", 1)[1]
    if ": " not in tail:
        return text
    return tail.split(": ", 1)[1].strip() or text


def _canonical_hierarchy_name(
    db: Session,
    *,
    title_type: TitleType,
    parent_id: int | None,
    season_number: int | None,
    episode_number: int | None,
    name: str,
) -> str:
    if title_type == TitleType.SEASON and parent_id is not None:
        series = db.query(Title).filter(Title.id == parent_id).first()
        if series:
            return _season_display_name(series.name, season_number)
    if title_type == TitleType.EPISODE:
        return _episode_title_name(name)
    return name


def normalize_hierarchy_names(db: Session) -> bool:
    changed = False
    seasons = db.query(Title).filter(Title.title_type == TitleType.SEASON).all()
    for season in seasons:
        if season.parent_id is None:
            continue
        expected = _canonical_hierarchy_name(
            db,
            title_type=TitleType.SEASON,
            parent_id=season.parent_id,
            season_number=season.season_number,
            episode_number=None,
            name=season.name,
        )
        if season.name != expected:
            season.name = expected
            changed = True

    episodes = db.query(Title).filter(Title.title_type == TitleType.EPISODE).all()
    for episode in episodes:
        if episode.parent_id is None:
            continue
        expected = _canonical_hierarchy_name(
            db,
            title_type=TitleType.EPISODE,
            parent_id=episode.parent_id,
            season_number=episode.season_number,
            episode_number=episode.episode_number,
            name=episode.name,
        )
        if episode.name != expected:
            episode.name = expected
            changed = True
    return changed


def _upsert_hierarchy_title(
    db: Session,
    *,
    external_id: str,
    slug: str,
    name: str,
    title_type: TitleType,
    parent_id: int | None,
    season_number: int | None = None,
    episode_number: int | None = None,
    synopsis: str | None = None,
    short_description: str | None = None,
    release_date_value: str | None = None,
    release_year: int | None = None,
    rating: str | None = None,
    genres: str | None = None,
    runtime_minutes: int | None = None,
    studio: str | None = None,
    cast: str | None = None,
    crew: str | None = None,
    poster_url: str | None = None,
    core_metadata: dict[str, str | None] | None = None,
) -> tuple[Title, bool]:
    name = _canonical_hierarchy_name(
        db,
        title_type=title_type,
        parent_id=parent_id,
        season_number=season_number,
        episode_number=episode_number,
        name=name,
    )
    title = _find_title_for_hierarchy(
        db,
        external_id=external_id,
        slug=slug,
        parent_id=parent_id,
    )
    created = title is None
    if title is None:
        title = Title(
            internal_id=_generate_unique_internal_id(db),
            slug=_unique_slug(db, slug),
            name=name,
            title_type=title_type,
            status=TitleStatus.DRAFT,
            parent_id=parent_id,
            season_number=season_number,
            episode_number=episode_number,
            synopsis=synopsis,
            short_description=short_description,
            release_date=_parse_iso_date(release_date_value),
            release_year=release_year,
            rating=rating,
            genres=genres,
            runtime_minutes=runtime_minutes,
            studio=studio,
            cast=cast,
            crew=crew,
            external_id=external_id,
            metadata_source="tmdb",
            poster_url=poster_url,
            metadata_json=_merge_metadata_json(None, core_metadata or {}),
        )
        db.add(title)
        db.flush()
        return title, True

    title.title_type = title_type
    _ensure_internal_id(db, title)
    title.parent_id = parent_id
    title.season_number = season_number
    title.episode_number = episode_number
    if not title.external_id:
        title.external_id = external_id
    if not title.metadata_source:
        title.metadata_source = "tmdb"
    if title.title_type in (TitleType.SEASON, TitleType.EPISODE):
        title.name = name
    else:
        _set_if_blank(title, "name", name)
    _set_if_blank(title, "synopsis", synopsis)
    _set_if_blank(title, "short_description", short_description)
    _set_if_blank(title, "release_date", _parse_iso_date(release_date_value))
    _set_if_blank(title, "release_year", release_year)
    _set_if_blank(title, "rating", rating)
    _set_if_blank(title, "genres", genres)
    _set_if_blank(title, "runtime_minutes", runtime_minutes)
    _set_if_blank(title, "studio", studio)
    _set_if_blank(title, "cast", cast)
    _set_if_blank(title, "crew", crew)
    _set_if_blank(title, "poster_url", poster_url)
    title.metadata_json = _merge_metadata_json(title.metadata_json, core_metadata or {})
    return title, created


def poster_urls_for_titles(db: Session, title_ids: list[int]) -> dict[int, str]:
    if not title_ids:
        return {}
    assets_by_title = _poster_assets_by_title(db, title_ids)
    titles = db.query(Title).filter(Title.id.in_(title_ids)).all()
    urls: dict[int, str] = {}
    for title in titles:
        cached = getattr(title, "poster_url", None)
        resolved = resolve_poster_url(
            cached_poster_url=cached,
            assets=assets_by_title.get(title.id, []),
        )
        if resolved:
            urls[title.id] = resolved
    return urls


def sync_title_poster_cache(db: Session, title_id: int) -> None:
    """Keep titles.poster_url aligned with the best catalog poster asset."""
    title = get_title(db, title_id)
    if not title:
        return
    assets = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.title_id == title_id,
            MediaAsset.asset_type.in_(_POSTER_TYPES),
        )
        .all()
    )
    best = pick_best_poster_uri(assets)
    if best and title.poster_url != best:
        title.poster_url = best
        db.commit()


def list_titles_read(
    db: Session,
    *,
    q: str | None = None,
    title_type: TitleType | None = None,
    parent_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[TitleRead]:
    titles = list_titles(
        db,
        q=q,
        title_type=title_type,
        parent_id=parent_id,
        skip=skip,
        limit=limit,
    )
    if _ensure_internal_ids(db, titles):
        db.commit()
    if normalize_hierarchy_names(db):
        db.commit()
    # List view uses titles.poster_url only — avoids media_assets enum/query failures on Neon.
    result: list[TitleRead] = []
    for title in titles:
        read = TitleRead.model_validate(title)
        read.poster_url = resolve_poster_url(
            cached_poster_url=getattr(title, "poster_url", None),
            assets=[],
        )
        result.append(read)
    return result


def get_title(db: Session, title_id: int) -> Title | None:
    return db.query(Title).filter(Title.id == title_id).first()


def get_title_read(db: Session, title_id: int) -> TitleRead | None:
    title = get_title(db, title_id)
    if not title:
        return None
    if not title.internal_id:
        _ensure_internal_id(db, title)
        db.commit()
        db.refresh(title)
    if normalize_hierarchy_names(db):
        db.commit()
        db.refresh(title)
    assets: list[MediaAsset] = []
    try:
        assets = (
            db.query(MediaAsset)
            .filter(
                MediaAsset.title_id == title_id,
                MediaAsset.asset_type.in_(_POSTER_TYPES),
            )
            .all()
        )
    except Exception:
        logger.warning(
            "poster asset query failed for title %s", title_id, exc_info=True
        )
        db.rollback()
    read = TitleRead.model_validate(title)
    read.poster_url = resolve_poster_url(
        cached_poster_url=getattr(title, "poster_url", None),
        assets=assets,
    )
    return read


def create_title(db: Session, payload: TitleCreate) -> Title:
    title = Title(**payload.model_dump(), internal_id=_generate_unique_internal_id(db))
    db.add(title)
    db.commit()
    db.refresh(title)
    return title


def update_title(db: Session, title: Title, payload: TitleUpdate) -> Title:
    _ensure_internal_id(db, title)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(title, key, value)
    db.commit()
    db.refresh(title)
    return title


def delete_title(db: Session, title: Title) -> None:
    db.delete(title)
    db.commit()


def annotate_series_hierarchy_preview(
    db: Session, preview: SeriesHierarchyPreview
) -> SeriesHierarchyPreview:
    series = _find_title_for_hierarchy(
        db,
        external_id=preview.external_id,
        slug=preview.slug,
        parent_id=None,
    )
    preview.existing_title_id = series.id if series else None
    preview.action = "update" if series else "create"
    series_parent_id = series.id if series else None

    for season in preview.seasons:
        existing_season = (
            _find_title_for_hierarchy(
                db,
                external_id=season.external_id,
                slug=season.slug,
                parent_id=series_parent_id,
            )
            if series_parent_id is not None
            else None
        )
        season.existing_title_id = existing_season.id if existing_season else None
        season.action = "update" if existing_season else "create"
        season_parent_id = existing_season.id if existing_season else None
        for episode in season.episodes:
            existing_episode = (
                _find_title_for_hierarchy(
                    db,
                    external_id=episode.external_id,
                    slug=episode.slug,
                    parent_id=season_parent_id,
                )
                if season_parent_id is not None
                else None
            )
            episode.existing_title_id = existing_episode.id if existing_episode else None
            episode.action = "update" if existing_episode else "create"
    return preview


def apply_series_hierarchy_preview(
    db: Session, preview: SeriesHierarchyPreview
) -> SeriesHierarchyApplyResult:
    created_count = 0
    updated_count = 0

    series, created = _upsert_hierarchy_title(
        db,
        external_id=preview.external_id,
        slug=preview.slug,
        name=preview.name,
        title_type=TitleType.SERIES,
        parent_id=None,
        synopsis=preview.synopsis,
        short_description=preview.short_description,
        release_date_value=preview.release_date,
        release_year=preview.release_year,
        rating=preview.rating,
        genres=preview.genres,
        runtime_minutes=preview.runtime_minutes,
        studio=preview.studio,
        cast=preview.cast,
        crew=preview.crew,
        poster_url=preview.poster_url,
        core_metadata=preview.core_metadata,
    )
    created_count += 1 if created else 0
    updated_count += 0 if created else 1

    for season_preview in preview.seasons:
        season, created = _upsert_hierarchy_title(
            db,
            external_id=season_preview.external_id,
            slug=season_preview.slug,
            name=season_preview.name,
            title_type=TitleType.SEASON,
            parent_id=series.id,
            season_number=season_preview.season_number,
            synopsis=season_preview.synopsis,
            release_date_value=season_preview.release_date,
            poster_url=season_preview.poster_url,
            core_metadata=season_preview.core_metadata,
        )
        created_count += 1 if created else 0
        updated_count += 0 if created else 1

        for episode_preview in season_preview.episodes:
            episode, created = _upsert_hierarchy_title(
                db,
                external_id=episode_preview.external_id,
                slug=episode_preview.slug,
                name=episode_preview.name,
                title_type=TitleType.EPISODE,
                parent_id=season.id,
                season_number=episode_preview.season_number,
                episode_number=episode_preview.episode_number,
                synopsis=episode_preview.synopsis,
                release_date_value=episode_preview.release_date,
                runtime_minutes=episode_preview.runtime_minutes,
                poster_url=episode_preview.still_url,
                core_metadata=episode_preview.core_metadata,
            )
            created_count += 1 if created else 0
            updated_count += 0 if created else 1

    db.commit()
    db.refresh(series)
    read = get_title_read(db, series.id) or TitleRead.model_validate(series)
    return SeriesHierarchyApplyResult(
        series=read,
        season_count=preview.season_count,
        episode_count=preview.episode_count,
        created_count=created_count,
        updated_count=updated_count,
    )


def build_title_tree(db: Session, root_id: int | None = None) -> list[Title]:
    titles = db.query(Title).order_by(Title.name).all()
    if _ensure_internal_ids(db, titles):
        db.commit()
    if normalize_hierarchy_names(db):
        db.commit()
        titles = db.query(Title).order_by(Title.name).all()
    by_parent: dict[int | None, list[Title]] = {}
    for title in titles:
        by_parent.setdefault(title.parent_id, []).append(title)

    def attach_children(title: Title) -> Title:
        title._tree_children = by_parent.get(title.id, [])  # type: ignore[attr-defined]
        for child in title._tree_children:  # type: ignore[attr-defined]
            attach_children(child)
        return title

    roots = by_parent.get(root_id, []) if root_id is not None else by_parent.get(None, [])
    return [attach_children(r) for r in roots]
