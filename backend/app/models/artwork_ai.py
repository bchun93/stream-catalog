import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.db_enums import str_enum
from app.models.media_asset import AssetType


class ArtworkRole(str, enum.Enum):
    VERTICAL_POSTER = "vertical_poster"
    BOX_ART = "box_art"
    HERO_IMAGE = "hero_image"
    HORIZONTAL_POSTER = "horizontal_poster"
    STILL_FRAME = "still_frame"
    LOGO = "logo"
    SEASON_POSTER = "season_poster"
    CAST_PHOTO = "cast_photo"
    UNKNOWN = "unknown"


class ArtworkTrainingDecision(str, enum.Enum):
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ArtworkTrainingExample(Base):
    __tablename__ = "artwork_training_examples"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int | None] = mapped_column(
        ForeignKey("titles.id"), nullable=True, index=True
    )
    candidate_uri: Mapped[str] = mapped_column(String(1024), index=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_asset_type: Mapped[AssetType | None] = mapped_column(
        str_enum(AssetType), nullable=True
    )
    assigned_role: Mapped[ArtworkRole] = mapped_column(
        str_enum(ArtworkRole, length=64), index=True
    )
    decision: Mapped[ArtworkTrainingDecision] = mapped_column(
        str_enum(ArtworkTrainingDecision),
        default=ArtworkTrainingDecision.APPROVED,
    )
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feature_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ArtworkClassification(Base):
    __tablename__ = "artwork_classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"), index=True)
    candidate_uri: Mapped[str] = mapped_column(String(1024), index=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_asset_type: Mapped[AssetType | None] = mapped_column(
        str_enum(AssetType), nullable=True
    )
    predicted_role: Mapped[ArtworkRole] = mapped_column(
        str_enum(ArtworkRole, length=64), index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model_version: Mapped[str] = mapped_column(String(64), default="baseline-v1")
    auto_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    feature_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
