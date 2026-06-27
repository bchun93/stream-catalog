import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.db_enums import str_enum


class PackageStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    DELIVERED = "delivered"
    ARCHIVED = "archived"


class DeliveryMode(str, enum.Enum):
    VOD = "vod"
    LINEAR = "linear"


class MonetizationModel(str, enum.Enum):
    SVOD = "svod"
    AVOD = "avod"
    TVOD = "tvod"
    FAST = "fast"


class DeliveryPackage(Base):
    __tablename__ = "delivery_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    buyer_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    deal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_mode: Mapped[DeliveryMode] = mapped_column(
        str_enum(DeliveryMode), default=DeliveryMode.VOD
    )
    monetization: Mapped[MonetizationModel] = mapped_column(
        str_enum(MonetizationModel), default=MonetizationModel.SVOD
    )
    status: Mapped[PackageStatus] = mapped_column(
        str_enum(PackageStatus), default=PackageStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
