from pydantic import BaseModel, Field

from app.models.title import TitleType
from app.schemas.artwork import ArtworkItem


class MetadataSearchResult(BaseModel):
    external_id: str = Field(description="Provider id, e.g. tmdb:movie:550")
    source: str = "tmdb"
    media_type: str = Field(description="movie or tv")
    title_type: TitleType
    name: str
    release_year: int | None = None
    overview: str | None = None
    poster_url: str | None = None


class TitleMetadataImport(BaseModel):
    """Descriptive metadata mapped for catalog title creation."""

    source: str = "tmdb"
    external_id: str
    media_type: str
    title_type: TitleType
    name: str
    slug: str | None = None
    synopsis: str | None = None
    short_description: str | None = None
    release_date: str | None = None
    release_year: int | None = None
    rating: str | None = None
    genres: str | None = None
    runtime_minutes: int | None = None
    studio: str | None = None
    licensor: str | None = None
    cast: str | None = None
    crew: str | None = None
    poster_url: str | None = None
    artwork: list[ArtworkItem] = Field(default_factory=list)
