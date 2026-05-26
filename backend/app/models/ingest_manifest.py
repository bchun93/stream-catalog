import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class IngestManifest(Base):
    __tablename__ = "ingest_manifests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rules_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    jobs: Mapped[list["IngestJob"]] = relationship(
        "IngestJob", back_populates="manifest", cascade="all, delete-orphan"
    )

    @property
    def rules(self) -> list[dict]:
        try:
            parsed = json.loads(self.rules_json or "[]")
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []


from app.models.ingest_job import IngestJob  # noqa: E402
