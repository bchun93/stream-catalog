from pydantic import BaseModel, Field

from app.models.title import TitleType
from app.schemas.artwork import ArtworkItem
from app.schemas.title import TitleRead


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
    core_metadata: dict[str, str | None] = Field(default_factory=dict)
    artwork: list[ArtworkItem] = Field(default_factory=list)


class EpisodeHierarchyPreview(BaseModel):
    external_id: str
    name: str
    slug: str
    season_number: int
    episode_number: int
    synopsis: str | None = None
    release_date: str | None = None
    runtime_minutes: int | None = None
    still_url: str | None = None
    core_metadata: dict[str, str | None] = Field(default_factory=dict)
    existing_title_id: int | None = None
    action: str = "create"


class SeasonHierarchyPreview(BaseModel):
    external_id: str
    name: str
    slug: str
    season_number: int
    synopsis: str | None = None
    release_date: str | None = None
    poster_url: str | None = None
    episode_count: int = 0
    core_metadata: dict[str, str | None] = Field(default_factory=dict)
    episodes: list[EpisodeHierarchyPreview] = Field(default_factory=list)
    existing_title_id: int | None = None
    action: str = "create"


class SeriesHierarchyPreview(BaseModel):
    external_id: str
    name: str
    slug: str
    synopsis: str | None = None
    short_description: str | None = None
    release_date: str | None = None
    release_year: int | None = None
    rating: str | None = None
    genres: str | None = None
    runtime_minutes: int | None = None
    studio: str | None = None
    cast: str | None = None
    crew: str | None = None
    poster_url: str | None = None
    core_metadata: dict[str, str | None] = Field(default_factory=dict)
    seasons: list[SeasonHierarchyPreview] = Field(default_factory=list)
    season_count: int = 0
    episode_count: int = 0
    existing_title_id: int | None = None
    action: str = "create"


class SeriesHierarchyApplyResult(BaseModel):
    series: TitleRead
    season_count: int
    episode_count: int
    created_count: int
    updated_count: int
