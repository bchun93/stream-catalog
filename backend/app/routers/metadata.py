import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_db
from app.models.title import TitleType
from app.schemas.metadata import (
    MetadataSearchResult,
    SeriesHierarchyApplyResult,
    SeriesHierarchyPreview,
    TitleMetadataImport,
)
from app.schemas.artwork import ArtworkItem
from app.services import title_service
from app.services.tmdb_service import (
    check_tmdb_connectivity,
    collect_artwork_from_tmdb,
    fetch_metadata,
    fetch_series_hierarchy_preview,
    parse_external_id,
    search_metadata,
)
from app.services.artwork_service import sync_hierarchy_artwork

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/health")
async def metadata_health():
    if not settings.tmdb_configured:
        return {
            "ok": False,
            "message": "TMDB_API_KEY is not set on Render. Add your v3 key under Environment and redeploy.",
            "tmdb_configured": False,
        }
    result = await check_tmdb_connectivity()
    result["tmdb_configured"] = True
    return result


@router.get("/search", response_model=list[MetadataSearchResult])
async def metadata_search(
    q: str = Query(..., min_length=1, description="Title name to look up"),
    title_type: TitleType | None = Query(
        None, description="Filter to movie or series results"
    ),
):
    try:
        return await search_metadata(q, title_type)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("metadata search failed for q=%r", q)
        raise HTTPException(
            status_code=500,
            detail=f"Metadata search failed: {exc}",
        ) from exc


@router.get("/artwork", response_model=list[ArtworkItem])
async def metadata_artwork(
    external_id: str = Query(..., description="TMDB id, e.g. tmdb:movie:550"),
):
    media_type, tmdb_id = parse_external_id(external_id)
    return await collect_artwork_from_tmdb(media_type, tmdb_id)


# Artwork path must be registered before the greedy /import/{external_id:path} route.
@router.get("/import/{external_id:path}/artwork", response_model=list[ArtworkItem])
async def metadata_import_artwork(external_id: str):
    media_type, tmdb_id = parse_external_id(external_id)
    return await collect_artwork_from_tmdb(media_type, tmdb_id)


@router.get("/hierarchy/preview", response_model=SeriesHierarchyPreview)
async def metadata_import_hierarchy_preview(
    external_id: str = Query(..., description="TMDB id, e.g. tmdb:tv:90296"),
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    media_type, tmdb_id = parse_external_id(external_id)
    if media_type != "tv":
        raise HTTPException(
            status_code=400,
            detail="Hierarchy import is only available for TMDB series.",
        )
    preview = await fetch_series_hierarchy_preview(tmdb_id)
    return title_service.annotate_series_hierarchy_preview(db, preview)


@router.post("/hierarchy/apply", response_model=SeriesHierarchyApplyResult)
async def metadata_import_hierarchy_apply(
    external_id: str = Query(..., description="TMDB id, e.g. tmdb:tv:90296"),
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    media_type, tmdb_id = parse_external_id(external_id)
    if media_type != "tv":
        raise HTTPException(
            status_code=400,
            detail="Hierarchy import is only available for TMDB series.",
        )
    preview = await fetch_series_hierarchy_preview(tmdb_id)
    result = title_service.apply_series_hierarchy_preview(db, preview)
    series = title_service.get_title(db, result.series.id)
    if series:
        await sync_hierarchy_artwork(db, series)
    return result


@router.get("/import/{external_id:path}", response_model=TitleMetadataImport)
async def metadata_import(external_id: str):
    media_type, tmdb_id = parse_external_id(external_id)
    return await fetch_metadata(media_type, tmdb_id)
