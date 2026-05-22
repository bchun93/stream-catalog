from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.media_asset import AssetType, MediaAsset
from app.models.title import Title, TitleType
from app.schemas.title import TitleCreate, TitleRead, TitleUpdate

_POSTER_TYPES = (
    AssetType.POSTER,
    AssetType.SEASON_POSTER,
    AssetType.THUMBNAIL,
)


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
            or_(Title.name.ilike(pattern), Title.slug.ilike(pattern))
        )
    if title_type:
        query = query.filter(Title.title_type == title_type)
    if parent_id is not None:
        query = query.filter(Title.parent_id == parent_id)
    return query.order_by(Title.updated_at.desc()).offset(skip).limit(limit).all()


def poster_urls_for_titles(db: Session, title_ids: list[int]) -> dict[int, str]:
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
    urls: dict[int, str] = {}
    for asset in assets:
        tid = asset.title_id
        if asset.asset_type == AssetType.POSTER:
            urls[tid] = asset.storage_uri
        elif tid not in urls:
            urls[tid] = asset.storage_uri
    return urls


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
    poster_map = poster_urls_for_titles(db, [t.id for t in titles])
    result: list[TitleRead] = []
    for title in titles:
        read = TitleRead.model_validate(title)
        read.poster_url = poster_map.get(title.id)
        result.append(read)
    return result


def get_title(db: Session, title_id: int) -> Title | None:
    return db.query(Title).filter(Title.id == title_id).first()


def create_title(db: Session, payload: TitleCreate) -> Title:
    title = Title(**payload.model_dump())
    db.add(title)
    db.commit()
    db.refresh(title)
    return title


def update_title(db: Session, title: Title, payload: TitleUpdate) -> Title:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(title, key, value)
    db.commit()
    db.refresh(title)
    return title


def delete_title(db: Session, title: Title) -> None:
    db.delete(title)
    db.commit()


def build_title_tree(db: Session, root_id: int | None = None) -> list[Title]:
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
