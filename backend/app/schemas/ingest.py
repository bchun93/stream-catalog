from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.ingest_job import IngestItemStatus, IngestJobStatus
from app.models.media_asset import AssetType


class IngestManifestRule(BaseModel):
    name: str | None = None
    pattern: str = Field(min_length=1)
    use_regex: bool = False
    asset_type: AssetType
    status: str = "uploaded"
    language: str | None = None
    resolution: str | None = None
    mime_type: str | None = None
    notes: str | None = None


class IngestManifestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: int
    description: str | None
    enabled: bool
    rules: list[IngestManifestRule]
    created_at: datetime
    updated_at: datetime


class IngestManifestValidateRequest(BaseModel):
    manifest_id: int
    source_prefix: str = Field(default="")
    max_keys: int | None = Field(default=None, ge=1, le=5000)


class IngestItemPreview(BaseModel):
    s3_key: str
    filename: str
    inferred_asset_type: AssetType | None = None
    language: str | None = None
    resolution: str | None = None
    matched_rule: str | None = None
    media_info: dict | None = None
    warnings: list[str] = Field(default_factory=list)


class IngestManifestValidateResponse(BaseModel):
    manifest_id: int
    source_prefix: str
    discovered_count: int
    matched_count: int
    skipped_count: int
    items: list[IngestItemPreview]


class IngestJobCreateRequest(BaseModel):
    title_id: int
    manifest_id: int
    source_prefix: str = Field(default="")
    created_by: str | None = None
    dry_run: bool = False
    max_keys: int | None = Field(default=None, ge=1, le=5000)

    @field_validator("source_prefix", mode="before")
    @classmethod
    def _normalize_prefix(cls, value: object) -> str:
        text = str(value or "").strip()
        return text.strip("/")


class IngestItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    s3_key: str
    filename: str
    inferred_asset_type: AssetType | None
    status: IngestItemStatus
    error_message: str | None
    resulting_asset_id: int | None
    created_at: datetime
    updated_at: datetime


class IngestJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title_id: int
    manifest_id: int | None
    source_prefix: str
    status: IngestJobStatus
    dry_run: bool
    created_by: str | None
    error_message: str | None
    discovered_count: int
    ingested_count: int
    skipped_count: int
    failed_count: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[IngestItemRead] | None = None
