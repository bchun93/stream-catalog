from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.artwork_ai import ArtworkRole, ArtworkTrainingDecision
from app.models.media_asset import AssetType
from app.schemas.artwork import ArtworkItem
from app.schemas.media_asset import MediaAssetRead


class ArtworkPrediction(BaseModel):
    item: ArtworkItem
    predicted_role: ArtworkRole
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str
    auto_apply: bool = False
    rationale: str | None = None


class ArtworkClassifyResponse(BaseModel):
    title_id: int
    threshold: float
    predictions: list[ArtworkPrediction]


class ArtworkAutoAssignRequest(BaseModel):
    threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    external_id: str | None = None


class ArtworkAutoAssignResponse(BaseModel):
    title_id: int
    threshold: float
    saved_count: int
    review_count: int
    assets: list[MediaAssetRead]
    predictions: list[ArtworkPrediction]


class ArtworkLabelRequest(BaseModel):
    title_id: int | None = None
    item: ArtworkItem
    assigned_role: ArtworkRole
    decision: ArtworkTrainingDecision = ArtworkTrainingDecision.APPROVED
    reviewer: str | None = None
    notes: str | None = None


class ArtworkTrainingExampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title_id: int | None = None
    candidate_uri: str
    filename: str | None = None
    source_asset_type: AssetType | None = None
    assigned_role: ArtworkRole
    decision: ArtworkTrainingDecision
    reviewer: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ArtworkReviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title_id: int
    candidate_uri: str
    filename: str | None = None
    source_asset_type: AssetType | None = None
    predicted_role: ArtworkRole
    confidence: float
    model_version: str
    rationale: str | None = None
    created_at: datetime
