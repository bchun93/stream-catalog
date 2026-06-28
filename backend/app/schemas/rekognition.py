from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Optional override of the S3 key to analyze (defaults to the asset's storage_uri).

    The key is interpreted within ``S3_ANALYSIS_BUCKET`` (decision 1A: analyze in place).
    """

    s3_key: str | None = Field(default=None, max_length=1024)


class FeatureResultRead(BaseModel):
    feature: str
    status: str
    aws_job_id: str | None = None
    started: bool
    message: str | None = None


class AnalyzeResponse(BaseModel):
    asset_id: int
    bucket: str
    key: str
    warnings: list[str] = []
    results: list[FeatureResultRead]


class RekognitionJobRead(BaseModel):
    asset_id: str
    feature: str
    aws_job_id: str | None = None
    status: str
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DetectionRead(BaseModel):
    sk: str
    feature: str
    kind: str | None = None
    name: str | None = None
    confidence: float | None = None
    timestamp_ms: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    bounding_box: dict[str, Any] | None = None
    job_id: str | None = None
    created_at: str | None = None


class ConsumeResponse(BaseModel):
    received: int
    processed: int
    deleted: int
    failed: int
    messages: list[str] = []
