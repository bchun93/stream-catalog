import json
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_sqlite_url() -> str:
    return f"sqlite:///{Path(__file__).resolve().parents[2] / 'data' / 'catalog.db'}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(default_factory=_default_sqlite_url)
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="CORS_ORIGINS",
    )
    # Auto-allow Amplify preview/production URLs (set to empty to disable).
    cors_origin_regex: str = Field(
        # Amplify (incl. main.d123.amplifyapp.com), CloudFront, Render, localhost.
        default=(
            r"https?://("
            r"localhost(:\d+)?|"
            r"127\.0\.0\.1(:\d+)?|"
            r"([a-z0-9-]+\.)*amplifyapp\.com|"
            r"([a-z0-9-]+\.)*cloudfront\.net|"
            r"([a-z0-9-]+\.)*onrender\.com"
            r")"
        ),
        validation_alias="CORS_ORIGIN_REGEX",
    )
    api_prefix: str = "/api/v1"
    seed_on_startup: bool = False
    port: int = 8000
    tmdb_api_key: str | None = Field(default=None, validation_alias="TMDB_API_KEY")
    tmdb_base_url: str = "https://api.themoviedb.org/3"

    @field_validator("tmdb_api_key", mode="before")
    @classmethod
    def _strip_tmdb_key(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def tmdb_configured(self) -> bool:
        key = self.tmdb_api_key
        if not key:
            return False
        return not (key.startswith("your_") or key == "your_tmdb_api_key_here")

    @property
    def cors_origins(self) -> list[str]:
        raw = self.cors_origins_raw.strip()
        if raw.startswith("["):
            return json.loads(raw)
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def cors_regex(self) -> str | None:
        value = (self.cors_origin_regex or "").strip()
        return value if value else None


settings = Settings()
