import json

from sqlalchemy.orm import Session

from app.models.metadata_config import MetadataFieldConfig
from app.schemas.metadata_config import (
    MetadataConfigRead,
    MetadataDisplaySettings,
)

CONFIG_KEY = "core_metadata_display"

METADATA_FIELD_KEYS: tuple[str, ...] = (
    "content_type",
    "movie_ref",
    "series_ref",
    "season_ref",
    "name",
    "synopsis",
    "short_synopsis",
    "season_count",
    "season_number",
    "episode_count",
    "episode_no",
    "copyright_line",
    "rating",
    "advisory",
    "release_date",
    "initial_release_year",
    "latest_release_year",
    "runtime",
    "studio",
    "genre",
    "language",
    "origin",
    "actors",
    "directors",
    "writers",
    "creators",
    "producers",
    "h_poster",
    "still_frame",
    "v_poster",
    "logo",
    "hero_image",
    "hero_image_vertical",
    "box_art",
    "source_file_name",
    "ad_dv",
    "hd_sd",
    "surround",
    "cc",
    "cc_language",
    "forced_narrative_cc",
    "forced_narrative_cc_language",
    "photosensitivity",
    "dubbing",
    "dubbing_language",
    "dub_cards",
    "skip_intro_start",
    "skip_intro_end",
    "skip_recap_start",
    "skip_recap_end",
    "skip_creds_start",
    "ad_breaks",
    "tags",
    "playback_start_date",
    "playback_end_date",
)

TITLE_TYPES: tuple[str, ...] = ("movie", "series", "season", "episode")


def default_settings() -> MetadataDisplaySettings:
    fields = list(METADATA_FIELD_KEYS)
    return MetadataDisplaySettings(
        movie=fields.copy(),
        series=fields.copy(),
        season=fields.copy(),
        episode=fields.copy(),
    )


def _clean_settings(raw: dict | MetadataDisplaySettings) -> MetadataDisplaySettings:
    values = raw.model_dump() if isinstance(raw, MetadataDisplaySettings) else raw
    allowed = set(METADATA_FIELD_KEYS)
    defaults = default_settings().model_dump()
    cleaned: dict[str, list[str]] = {}
    for title_type in TITLE_TYPES:
        incoming = values.get(title_type, defaults[title_type])
        if not isinstance(incoming, list):
            incoming = defaults[title_type]
        seen: set[str] = set()
        cleaned[title_type] = [
            key
            for key in incoming
            if isinstance(key, str) and key in allowed and not (key in seen or seen.add(key))
        ]
    return MetadataDisplaySettings(**cleaned)


def _read_settings(config: MetadataFieldConfig) -> MetadataDisplaySettings:
    return _clean_settings(config.settings)


def _to_read(config: MetadataFieldConfig) -> MetadataConfigRead:
    return MetadataConfigRead(
        key=config.key,
        settings=_read_settings(config),
        defaults=default_settings(),
        updated_at=config.updated_at,
    )


def ensure_config(db: Session) -> MetadataFieldConfig:
    config = db.query(MetadataFieldConfig).filter(MetadataFieldConfig.key == CONFIG_KEY).first()
    if config:
        return config
    config = MetadataFieldConfig(
        key=CONFIG_KEY,
        settings_json=json.dumps(default_settings().model_dump()),
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def get_config(db: Session) -> MetadataConfigRead:
    return _to_read(ensure_config(db))


def update_config(db: Session, settings: MetadataDisplaySettings) -> MetadataConfigRead:
    config = ensure_config(db)
    cleaned = _clean_settings(settings)
    config.settings_json = json.dumps(cleaned.model_dump())
    db.commit()
    db.refresh(config)
    return _to_read(config)
