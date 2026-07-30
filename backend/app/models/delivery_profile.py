"""Delivery profile — platform/channel technical acceptance contract."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DeliveryProfile(Base):
    __tablename__ = "delivery_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(120), index=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)  # svod|avod|tvod|fast
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    spec_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    packages: Mapped[list["DeliveryPackage"]] = relationship(
        "DeliveryPackage",
        back_populates="profile",
    )

    @property
    def spec(self) -> dict:
        try:
            parsed = json.loads(self.spec_json or "{}")
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
