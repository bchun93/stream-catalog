from fastapi import APIRouter, Query

from app.models.title import TitleType
from app.schemas.metadata import MetadataSearchResult, TitleMetadataImport
from app.services.tmdb_service import fetch_metadata, parse_external_id, search_metadata

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/search", response_model=list[MetadataSearchResult])
async def metadata_search(
    q: str = Query(..., min_length=1, description="Title name to look up"),
    title_type: TitleType | None = Query(
        None, description="Filter to movie or series results"
    ),
):
    return await search_metadata(q, title_type)


@router.get("/import/{external_id:path}", response_model=TitleMetadataImport)
async def metadata_import(external_id: str):
    media_type, tmdb_id = parse_external_id(external_id)
    return await fetch_metadata(media_type, tmdb_id)
