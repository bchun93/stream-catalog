from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MetadataDisplaySettings(BaseModel):
    movie: list[str] = []
    series: list[str] = []
    season: list[str] = []
    episode: list[str] = []


class MetadataConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    settings: MetadataDisplaySettings
    defaults: MetadataDisplaySettings
    updated_at: datetime | None = None


class MetadataConfigUpdate(BaseModel):
    settings: MetadataDisplaySettings
