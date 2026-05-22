from pydantic import BaseModel, Field, field_validator

from app.models.media_asset import AssetType


def _coerce_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

    @field_validator("width", "height", "vote_count", mode="before")
    @classmethod
    def _int_fields(cls, value: object) -> int | None:
        return _coerce_int(value)

    @field_validator("aspect_ratio", "vote_average", mode="before")
    @classmethod
    def _float_fields(cls, value: object) -> float | None:
        return _coerce_float(value)


class ArtworkItem(BaseModel):
    """Artwork from TMDB (preview or persisted as MediaAsset)."""

    asset_type: AssetType
    storage_uri: str = Field(max_length=1024)
    filename: str = Field(max_length=255)
    mime_type: str | None = "image/jpeg"
    language: str | None = None
    resolution: str | None = None
    notes: str | None = None
    specs: ArtworkSpecs | None = None


class SaveArtworkRequest(BaseModel):
    """User-selected artwork to persist for a title."""

    items: list[ArtworkItem] = Field(min_length=1)
