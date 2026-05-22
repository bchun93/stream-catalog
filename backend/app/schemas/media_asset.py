from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.media_asset import AssetStatus, AssetType
from app.schemas.artwork import ArtworkSpecs


class MediaAssetBase(BaseModel):
    title_id: int
    asset_type: AssetType
    status: AssetStatus = AssetStatus.UPLOADED
    filename: str = Field(max_length=255)
    mime_type: str | None = None
    storage_uri: str = Field(max_length=1024)
    size_bytes: int | None = None
    checksum: str | None = None
    language: str | None = None
    resolution: str | None = None
    duration_seconds: int | None = None
    codec: str | None = None
    version: int = 1
    notes: str | None = None
    metadata_json: str | None = None


class MediaAssetCreate(MediaAssetBase):
    pass


class MediaAssetUpdate(BaseModel):
    asset_type: AssetType | None = None
    status: AssetStatus | None = None
    filename: str | None = None
    mime_type: str | None = None
    storage_uri: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    language: str | None = None
    resolution: str | None = None
    duration_seconds: int | None = None
    codec: str | None = None
    version: int | None = None
    notes: str | None = None
    metadata_json: str | None = None


class MediaAssetRead(MediaAssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    specs: ArtworkSpecs | None = None
