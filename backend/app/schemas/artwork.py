from pydantic import BaseModel, Field

from app.models.media_asset import AssetType


class ArtworkItem(BaseModel):
    """Artwork from TMDB (preview or persisted as MediaAsset)."""

    asset_type: AssetType
    storage_uri: str = Field(max_length=1024)
    filename: str = Field(max_length=255)
    mime_type: str | None = "image/jpeg"
    language: str | None = None
    resolution: str | None = None
    notes: str | None = None
