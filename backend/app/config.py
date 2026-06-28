import json
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_sqlite_url() -> str:
    return f"sqlite:///{Path(__file__).resolve().parents[2] / 'data' / 'catalog.db'}"


def _normalize_database_url(value: str) -> str:
    text = value.strip().strip('"').strip("'")
    if text.startswith("postgres://"):
        text = "postgresql://" + text[len("postgres://") :]
    return text


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(
        default_factory=_default_sqlite_url,
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
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
    ingest_s3_bucket: str | None = Field(default=None, validation_alias="INGEST_S3_BUCKET")
    ingest_s3_prefix: str = Field(default="", validation_alias="INGEST_S3_PREFIX")
    aspera_drop_prefix: str = Field(default="", validation_alias="ASPERA_DROP_PREFIX")
    ingest_operator_token: str | None = Field(
        default=None, validation_alias="INGEST_OPERATOR_TOKEN"
    )
    admin_api_key: str | None = Field(default=None, validation_alias="ADMIN_API_KEY")
    ingest_max_keys: int = Field(default=1000, validation_alias="INGEST_MAX_KEYS")
    aws_profile: str | None = Field(default=None, validation_alias="AWS_PROFILE")
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_REGION")
    aws_access_key_id: str | None = Field(default=None, validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(
        default=None, validation_alias="AWS_SECRET_ACCESS_KEY"
    )
    aws_endpoint_url: str | None = Field(default=None, validation_alias="AWS_ENDPOINT_URL")

    # --- Amazon Rekognition Video integration ---
    s3_analysis_bucket: str | None = Field(
        default=None, validation_alias="S3_ANALYSIS_BUCKET"
    )
    rekognition_role_arn: str | None = Field(
        default=None, validation_alias="REKOGNITION_ROLE_ARN"
    )
    rekognition_sns_topic_arn: str | None = Field(
        default=None, validation_alias="REKOGNITION_SNS_TOPIC_ARN"
    )
    rekognition_sqs_queue_url: str | None = Field(
        default=None, validation_alias="REKOGNITION_SQS_QUEUE_URL"
    )
    ddb_jobs_table: str = Field(
        default="relay_rekognition_jobs", validation_alias="DDB_JOBS_TABLE"
    )
    ddb_detections_table: str = Field(
        default="relay_rekognition_detections", validation_alias="DDB_DETECTIONS_TABLE"
    )
    rekognition_consumer_secret: str | None = Field(
        default=None, validation_alias="REKOGNITION_CONSUMER_SECRET"
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_db_url(cls, value: object) -> object:
        if isinstance(value, str):
            return _normalize_database_url(value)
        return value

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

    @property
    def rekognition_configured(self) -> bool:
        """True when the minimum AWS wiring for starting jobs is present."""
        return bool(
            (self.rekognition_role_arn or "").strip()
            and (self.rekognition_sns_topic_arn or "").strip()
        )


settings = Settings()
