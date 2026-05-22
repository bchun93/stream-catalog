from pydantic import BaseModel, Field

from app.models.media_asset import AssetType


class ArtworkSpecs(BaseModel):
    """Technical metadata from TMDB (when available)."""

    width: int | None = None
    height: int | None = None
    aspect_ratio: float | None = None
    aspect_ratio_label: str | None = Field(
        None, description="Human-readable ratio, e.g. 2:3 or 16:9"
    )
    resolution: str | None = Field(None, description="WxH pixels")
    language: str | None = Field(None, description="ISO 639-1, e.g. en")
    country: str | None = Field(None, description="ISO 3166-1, when provided by TMDB")
    vote_average: float | None = None
    vote_count: int | None = None
    label: str | None = Field(None, description="Cast name, season number, etc.")


class ArtworkItem(BaseModel):
    """Artwork from TMDB (preview or persisted as MediaAsset)."""

    asset_type: AssetType
    storage_uri: str = Field(max_length=1024)
    filename: str = Field(max_length=255)
    mime_type: str | None = "image/jpeg"
    language: str | None = None
    resolution: str | None = None
    notes: str | None = None
    specs: ArtworkSpecs = Field(default_factory=ArtworkSpecs)


class SaveArtworkRequest(BaseModel):
    """User-selected artwork to persist for a title."""

    items: list[ArtworkItem] = Field(min_length=1)
