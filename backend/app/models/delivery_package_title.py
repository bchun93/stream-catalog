from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DeliveryPackageTitle(Base):
    __tablename__ = "delivery_package_titles"
    __table_args__ = (
        UniqueConstraint("package_id", "title_id", name="uq_delivery_package_title"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_packages.id", ondelete="CASCADE"), index=True
    )
    title_id: Mapped[int] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    package: Mapped["DeliveryPackage"] = relationship(
        "DeliveryPackage", back_populates="package_titles"
    )
    title: Mapped["Title"] = relationship("Title")


from app.models.delivery_package import DeliveryPackage  # noqa: E402
from app.models.title import Title  # noqa: E402
