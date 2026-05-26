from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.title import TitleStatus, TitleType


class TitleBase(BaseModel):
    slug: str = Field(max_length=120)
    name: str = Field(max_length=255)
    title_type: TitleType
    status: TitleStatus = TitleStatus.DRAFT
    synopsis: str | None = None
    short_description: str | None = None
    release_date: date | None = None
    rating: str | None = None
    genres: str | None = None
    territories: str | None = None
    availability_start: date | None = None
    availability_end: date | None = None
    parent_id: int | None = None
    season_number: int | None = None
    episode_number: int | None = None
    runtime_minutes: int | None = None
    release_year: int | None = None
    licensor: str | None = None
    studio: str | None = None
    cast: str | None = None
    crew: str | None = None
    eidr: str | None = None
    external_id: str | None = None
    metadata_source: str | None = None
    poster_url: str | None = None
    metadata_json: str | None = None


class TitleCreate(TitleBase):
    pass


class TitleUpdate(BaseModel):
    slug: str | None = None
    name: str | None = None
    title_type: TitleType | None = None
    status: TitleStatus | None = None
    synopsis: str | None = None
    short_description: str | None = None
    release_date: date | None = None
    rating: str | None = None
    genres: str | None = None
    territories: str | None = None
    availability_start: date | None = None
    availability_end: date | None = None
    parent_id: int | None = None
    season_number: int | None = None
    episode_number: int | None = None
    runtime_minutes: int | None = None
    release_year: int | None = None
    licensor: str | None = None
    studio: str | None = None
    cast: str | None = None
    crew: str | None = None
    eidr: str | None = None
    external_id: str | None = None
    metadata_source: str | None = None
    poster_url: str | None = None
    metadata_json: str | None = None


class TitleRead(TitleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class TitleTree(TitleRead):
    children: list["TitleTree"] = []


TitleTree.model_rebuild()
