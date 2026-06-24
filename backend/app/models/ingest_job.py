import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.db_enums import str_enum
from app.models.media_asset import AssetType


class IngestJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestItemStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    SKIPPED = "skipped"
    INGESTED = "ingested"
    FAILED = "failed"


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"), index=True)
    manifest_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingest_manifests.id"), nullable=True, index=True
    )
    source_prefix: Mapped[str] = mapped_column(String(512))
    status: Mapped[IngestJobStatus] = mapped_column(
        str_enum(IngestJobStatus), default=IngestJobStatus.PENDING, index=True
    )
    dry_run: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    title: Mapped["Title"] = relationship("Title")
    manifest: Mapped["IngestManifest | None"] = relationship(
        "IngestManifest", back_populates="jobs"
    )
    items: Mapped[list["IngestItem"]] = relationship(
        "IngestItem", back_populates="job", cascade="all, delete-orphan"
    )


class IngestItem(Base):
    __tablename__ = "ingest_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("ingest_jobs.id"), index=True)
    s3_key: Mapped[str] = mapped_column(String(1024), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    inferred_asset_type: Mapped[AssetType | None] = mapped_column(
        str_enum(AssetType), nullable=True
    )
    status: Mapped[IngestItemStatus] = mapped_column(
        str_enum(IngestItemStatus),
        default=IngestItemStatus.DISCOVERED,
        index=True,
    )
    media_info_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    job: Mapped[IngestJob] = relationship("IngestJob", back_populates="items")
    resulting_asset: Mapped["MediaAsset | None"] = relationship("MediaAsset")


from app.models.ingest_manifest import IngestManifest  # noqa: E402
from app.models.media_asset import MediaAsset  # noqa: E402
from app.models.title import Title  # noqa: E402
