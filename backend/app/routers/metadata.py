import logging

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.title import TitleType
from app.schemas.metadata import MetadataSearchResult, TitleMetadataImport
from app.schemas.artwork import ArtworkItem
from app.services.tmdb_service import (
    check_tmdb_connectivity,
    collect_artwork_from_tmdb,
    fetch_metadata,
    parse_external_id,
    search_metadata,
)

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


@router.get("/import/{external_id:path}", response_model=TitleMetadataImport)
async def metadata_import(external_id: str):
    media_type, tmdb_id = parse_external_id(external_id)
    return await fetch_metadata(media_type, tmdb_id)
