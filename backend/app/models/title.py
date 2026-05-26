import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TitleType(str, enum.Enum):
    MOVIE = "movie"
    SERIES = "series"
    SEASON = "season"
    EPISODE = "episode"


class TitleStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Title(Base):
    __tablename__ = "titles"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    title_type: Mapped[TitleType] = mapped_column(
        Enum(TitleType, native_enum=False)
    )
    status: Mapped[TitleStatus] = mapped_column(
        Enum(TitleStatus, native_enum=False), default=TitleStatus.DRAFT
    )
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    genres: Mapped[str | None] = mapped_column(String(500), nullable=True)
    territories: Mapped[str | None] = mapped_column(String(500), nullable=True)
    availability_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    availability_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("titles.id"), nullable=True, index=True
    )
    season_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    licensor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    studio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cast: Mapped[str | None] = mapped_column(Text, nullable=True)
    crew: Mapped[str | None] = mapped_column(Text, nullable=True)
    eidr: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    parent: Mapped["Title | None"] = relationship(
        "Title", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Title"]] = relationship("Title", back_populates="parent")
    media_assets: Mapped[list["MediaAsset"]] = relationship(
        "MediaAsset", back_populates="title", cascade="all, delete-orphan"
    )


from app.models.media_asset import MediaAsset  # noqa: E402
