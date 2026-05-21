from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.title import Title, TitleType
from app.schemas.media_asset import MediaAssetRead
from app.schemas.title import TitleCreate, TitleRead, TitleTree, TitleUpdate
from app.services import title_service
from app.services.artwork_service import sync_artwork_for_title

router = APIRouter(prefix="/titles", tags=["titles"])


def _title_to_tree(title) -> TitleTree:
    children = getattr(title, "_tree_children", [])
    data = TitleRead.model_validate(title).model_dump()
    return TitleTree(**data, children=[_title_to_tree(c) for c in children])


@router.get("", response_model=list[TitleRead])
def list_titles(
    q: str | None = Query(None, description="Search name or slug"),
    title_type: TitleType | None = None,
    parent_id: int | None = None,
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    return title_service.list_titles(
        db, q=q, title_type=title_type, parent_id=parent_id, skip=skip, limit=limit
    )


@router.get("/tree", response_model=list[TitleTree])
def get_title_tree(db: Session = Depends(get_db)):
    roots = title_service.build_title_tree(db)
    return [_title_to_tree(r) for r in roots]


@router.get("/{title_id}", response_model=TitleRead)
def get_title(title_id: int, db: Session = Depends(get_db)):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    return title


@router.post("", response_model=TitleRead, status_code=201)
async def create_title(payload: TitleCreate, db: Session = Depends(get_db)):
    existing = db.query(Title).filter(Title.slug == payload.slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="Slug already exists")
    title = title_service.create_title(db, payload)
    if title.external_id and title.external_id.startswith("tmdb:"):
        await sync_artwork_for_title(db, title)
    return title


@router.post("/{title_id}/artwork/sync", response_model=list[MediaAssetRead])
async def sync_title_artwork(title_id: int, db: Session = Depends(get_db)):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    if not title.external_id or not title.external_id.startswith("tmdb:"):
        raise HTTPException(
            status_code=400,
            detail="Title has no TMDB external_id — import metadata first",
        )
    return await sync_artwork_for_title(db, title)


@router.patch("/{title_id}", response_model=TitleRead)
def update_title(
    title_id: int, payload: TitleUpdate, db: Session = Depends(get_db)
):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    return title_service.update_title(db, title, payload)


@router.delete("/{title_id}", status_code=204)
def delete_title(title_id: int, db: Session = Depends(get_db)):
    title = title_service.get_title(db, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    title_service.delete_title(db, title)
    return None
