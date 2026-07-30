"""Pydantic schemas for delivery profiles and validation findings."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DeliveryProfileSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    platform: str
    channel: str
    version: int
    description: str | None = None
    enabled: bool = True


class DeliveryProfileRead(DeliveryProfileSummary):
    spec: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ValidationFinding(BaseModel):
    rule_id: str
    section: str
    status: Literal["pass", "fail", "skip"]
    message: str
    title_id: int | None = None
    title_name: str | None = None
    asset_id: int | None = None
    observed: str | None = None
    expected: str | None = None


class PackageValidationResponse(BaseModel):
    package_id: int
    profile_id: int
    profile_slug: str
    summary: Literal["pass", "fail", "incomplete"]
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    findings: list[ValidationFinding] = Field(default_factory=list)
