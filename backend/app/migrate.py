import logging
import json
import secrets

from sqlalchemy import inspect, text

from app.database import engine
from app.models.artwork_ai import ArtworkRole, ArtworkTrainingDecision
from app.models.ingest_job import IngestItemStatus, IngestJobStatus
from app.models.media_asset import AssetStatus, AssetType
from app.models.title import TitleStatus, TitleType
from app.services.metadata_config_service import CONFIG_KEY, default_settings

logger = logging.getLogger(__name__)

_NEW_COLUMNS = [
    ("internal_id", "VARCHAR(32)"),
    ("release_year", "INTEGER"),
    ("licensor", "VARCHAR(255)"),
    ("studio", "VARCHAR(500)"),
    ("cast", "TEXT"),
    ("crew", "TEXT"),
    ("eidr", "VARCHAR(128)"),
    ("external_id", "VARCHAR(64)"),
    ("metadata_source", "VARCHAR(32)"),
    ("poster_url", "VARCHAR(1024)"),
    ("metadata_json", "TEXT"),
]

_INTERNAL_ID_PREFIX = "SC"

_MEDIA_ASSET_COLUMNS = [
    ("metadata_json", "TEXT"),
]

# Legacy Postgres enum type names (from early deploys).
_PG_ENUM_TYPES = (
    "assettype",
    "assetstatus",
    "titletype",
    "titlestatus",
    "ingestjobstatus",
    "ingestitemstatus",
    "artworkrole",
    "artworktrainingdecision",
)

# Columns that must be VARCHAR to match SQLAlchemy native_enum=False + SQLite locally.
_PG_ENUM_COLUMNS: tuple[tuple[str, str, int], ...] = (
    ("media_assets", "asset_type", 32),
    ("media_assets", "status", 32),
    ("titles", "title_type", 32),
    ("titles", "status", 32),
    ("ingest_jobs", "status", 32),
    ("ingest_items", "inferred_asset_type", 32),
    ("ingest_items", "status", 32),
    ("artwork_training_examples", "source_asset_type", 32),
    ("artwork_training_examples", "assigned_role", 64),
    ("artwork_training_examples", "decision", 32),
    ("artwork_classifications", "source_asset_type", 32),
    ("artwork_classifications", "predicted_role", 64),
)


def _quote_ident(name: str) -> str:
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def _pg_column_udt_name(conn, table: str, column: str) -> str | None:
    row = conn.execute(
        text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table, "column_name": column},
    ).fetchone()
    return row[0] if row else None


def _needs_varchar_migration(conn, table: str, column: str) -> bool:
    udt = _pg_column_udt_name(conn, table, column)
    if not udt:
        return False
    if udt in _PG_ENUM_TYPES:
        return True
    if udt not in ("varchar", "text", "bpchar"):
        return True
    return False


def _upgrade_postgres_enums_to_varchar(conn) -> None:
    """Convert legacy native PG enums to VARCHAR so all AssetType values work."""
    inspector = inspect(conn)
    for table, column, varchar_len in _PG_ENUM_COLUMNS:
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if column not in cols:
            continue
        if not _needs_varchar_migration(conn, table, column):
            continue

        col_ident = _quote_ident(column)
        table_ident = _quote_ident(table)
        logger.info("Migrating %s.%s from PG enum to VARCHAR(%s)", table, column, varchar_len)

        conn.execute(
            text(
                f"ALTER TABLE {table_ident} "
                f"ALTER COLUMN {col_ident} TYPE VARCHAR({varchar_len}) "
                f"USING LOWER({col_ident}::text)"
            )
        )

    # Leave legacy enum types in place after column migration. Dropping enum types can
    # abort the whole startup migration if any old dependency remains on Neon.


def _ensure_pg_enum_values(conn) -> None:
    """If enum columns still exist, add missing labels (fallback)."""

    def _enum_labels(enum_cls) -> list[str]:
        labels: list[str] = []
        for item in enum_cls:
            for label in (item.name, str(item.value)):
                if label not in labels:
                    labels.append(label)
        return labels

    additions = {
        "assettype": _enum_labels(AssetType),
        "assetstatus": _enum_labels(AssetStatus),
        "titletype": _enum_labels(TitleType),
        "titlestatus": _enum_labels(TitleStatus),
        "ingestjobstatus": _enum_labels(IngestJobStatus),
        "ingestitemstatus": _enum_labels(IngestItemStatus),
        "artworkrole": _enum_labels(ArtworkRole),
        "artworktrainingdecision": _enum_labels(ArtworkTrainingDecision),
    }
    for type_name, labels in additions.items():
        for label in labels:
            safe_label = label.replace("'", "''")
            try:
                conn.execute(text("SAVEPOINT enum_label_add"))
                conn.execute(
                    text(
                        f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{safe_label}'"
                    )
                )
                conn.execute(text("RELEASE SAVEPOINT enum_label_add"))
            except Exception:
                conn.execute(text("ROLLBACK TO SAVEPOINT enum_label_add"))


def _seed_default_ingest_manifest(conn) -> None:
    existing = conn.execute(
        text("SELECT id FROM ingest_manifests WHERE name = :name AND version = 1 LIMIT 1"),
        {"name": "ott-default-v1"},
    ).fetchone()
    if existing:
        return
    default_rules = [
        {
            "name": "video-master",
            "pattern": "*master*.mp4",
            "asset_type": "video_master",
            "status": "uploaded",
        },
        {
            "name": "video-trailer",
            "pattern": "*trailer*.mp4",
            "asset_type": "trailer",
            "status": "uploaded",
        },
        {
            "name": "audio",
            "pattern": "*audio*.*",
            "asset_type": "audio",
            "status": "uploaded",
        },
        {
            "name": "subtitle",
            "pattern": "*.{srt,vtt}",
            "asset_type": "subtitle",
            "status": "uploaded",
        },
        {
            "name": "caption",
            "pattern": "*caption*.*",
            "asset_type": "caption",
            "status": "uploaded",
        },
    ]
    conn.execute(
        text(
            """
            INSERT INTO ingest_manifests
            (name, version, description, rules_json, enabled, created_at, updated_at)
            VALUES
            (:name, :version, :description, :rules_json, :enabled, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        ),
        {
            "name": "ott-default-v1",
            "version": 1,
            "description": "Starter OTT ingest rules for common file naming conventions.",
            "rules_json": json.dumps(default_rules),
            "enabled": True,
        },
    )


def _seed_default_metadata_config(conn) -> None:
    existing = conn.execute(
        text("SELECT id FROM metadata_field_configs WHERE key = :key LIMIT 1"),
        {"key": CONFIG_KEY},
    ).fetchone()
    if existing:
        return
    conn.execute(
        text(
            """
            INSERT INTO metadata_field_configs
            (key, settings_json, created_at, updated_at)
            VALUES
            (:key, :settings_json, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        ),
        {
            "key": CONFIG_KEY,
            "settings_json": json.dumps(default_settings().model_dump()),
        },
    )


def _new_internal_id() -> str:
    return f"{_INTERNAL_ID_PREFIX}-{secrets.token_hex(6).upper()}"


def _ensure_title_internal_ids(conn) -> None:
    inspector = inspect(conn)
    if "titles" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("titles")}
    if "internal_id" not in cols:
        return

    existing = {
        row[0]
        for row in conn.execute(
            text("SELECT internal_id FROM titles WHERE internal_id IS NOT NULL")
        ).fetchall()
        if row[0]
    }
    rows = conn.execute(
        text("SELECT id FROM titles WHERE internal_id IS NULL OR internal_id = ''")
    ).fetchall()
    for row in rows:
        while True:
            candidate = _new_internal_id()
            if candidate not in existing:
                existing.add(candidate)
                break
        conn.execute(
            text("UPDATE titles SET internal_id = :internal_id WHERE id = :id"),
            {"internal_id": candidate, "id": row[0]},
        )


def _normalize_hierarchy_names(conn) -> None:
    inspector = inspect(conn)
    if "titles" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("titles")}
    required = {"id", "name", "title_type", "parent_id", "season_number", "episode_number"}
    if not required.issubset(cols):
        return

    rows = conn.execute(
        text(
            """
            SELECT id, name, title_type, parent_id, season_number, episode_number
            FROM titles
            WHERE title_type IN ('season', 'episode', 'SEASON', 'EPISODE')
            """
        )
    ).fetchall()
    by_id = {
        row[0]: {
            "id": row[0],
            "name": row[1],
            "title_type": str(row[2]).lower() if row[2] is not None else "",
            "parent_id": row[3],
            "season_number": row[4],
            "episode_number": row[5],
        }
        for row in rows
    }

    def episode_title_name(current_name: str | None, episode_number: int | None) -> str:
        text_value = str(current_name or f"Episode {episode_number or 1}").strip()
        if ": Episode " not in text_value:
            return text_value
        tail = text_value.split(": Episode ", 1)[1]
        if ": " not in tail:
            return text_value
        return tail.split(": ", 1)[1].strip() or text_value

    for row in rows:
        title_id, current_name, raw_type, parent_id, season_number, episode_number = row
        title_type = str(raw_type).lower() if raw_type is not None else ""
        if parent_id is None:
            continue
        parent = by_id.get(parent_id)
        if parent is None:
            parent_row = conn.execute(
                text("SELECT id, name, title_type, parent_id, season_number FROM titles WHERE id = :id"),
                {"id": parent_id},
            ).fetchone()
            if parent_row:
                parent = {
                    "id": parent_row[0],
                    "name": parent_row[1],
                    "title_type": str(parent_row[2]).lower() if parent_row[2] is not None else "",
                    "parent_id": parent_row[3],
                    "season_number": parent_row[4],
                }
                by_id[parent_id] = parent
        if not parent:
            continue

        expected = None
        if title_type == "season":
            season_label = "Specials" if season_number == 0 else f"Season {season_number or 1}"
            expected = f"{parent['name']}: {season_label}"
        elif title_type == "episode":
            expected = episode_title_name(current_name, episode_number)

        if expected and current_name != expected:
            conn.execute(
                text("UPDATE titles SET name = :name WHERE id = :id"),
                {"name": expected, "id": title_id},
            )


def _ensure_common_indexes(conn) -> None:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())

    if "titles" in tables:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_titles_internal_id "
                "ON titles (internal_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_titles_updated_at "
                "ON titles (updated_at DESC)"
            )
        )
    if "media_assets" in tables:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_media_assets_title_type_updated "
                "ON media_assets (title_id, asset_type, updated_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_media_assets_storage_uri "
                "ON media_assets (storage_uri)"
            )
        )
    if "artwork_training_examples" in tables:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_artwork_training_role "
                "ON artwork_training_examples (assigned_role)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_artwork_training_uri "
                "ON artwork_training_examples (candidate_uri)"
            )
        )
    if "artwork_classifications" in tables:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_artwork_classifications_title "
                "ON artwork_classifications (title_id, confidence DESC)"
            )
        )


def run_migrations() -> None:
    if engine.dialect.name == "postgresql":
        host = engine.url.host or ""
        if "pooler" in host:
            logger.warning(
                "DATABASE_URL uses a Neon pooler host (%s). Continuing migrations; "
                "if schema updates fail, switch to Neon direct connection URL.",
                host,
            )

    inspector = inspect(engine)

    if "titles" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("titles")}
        with engine.begin() as conn:
            for name, col_type in _NEW_COLUMNS:
                if name not in existing:
                    col = _quote_ident(name)
                    conn.execute(
                        text(f"ALTER TABLE titles ADD COLUMN {col} {col_type}")
                    )

    if "media_assets" in inspector.get_table_names():
        asset_cols = {col["name"] for col in inspector.get_columns("media_assets")}
        with engine.begin() as conn:
            for name, col_type in _MEDIA_ASSET_COLUMNS:
                if name not in asset_cols:
                    col = _quote_ident(name)
                    conn.execute(
                        text(f"ALTER TABLE media_assets ADD COLUMN {col} {col_type}")
                    )

    if engine.dialect.name == "postgresql":
        # Commit enum→VARCHAR first — a later failure must not roll this back.
        with engine.begin() as conn:
            _upgrade_postgres_enums_to_varchar(conn)

        with engine.begin() as conn:
            _ensure_pg_enum_values(conn)

        with engine.begin() as conn:
            _ensure_title_internal_ids(conn)
            _normalize_hierarchy_names(conn)
            _ensure_common_indexes(conn)
            tables = set(inspect(conn).get_table_names())
            if "ingest_manifests" in tables:
                _seed_default_ingest_manifest(conn)
            if "metadata_field_configs" in tables:
                _seed_default_metadata_config(conn)
    else:
        with engine.begin() as conn:
            _ensure_title_internal_ids(conn)
            _normalize_hierarchy_names(conn)
            _ensure_common_indexes(conn)
            tables = set(inspect(conn).get_table_names())
            if "ingest_manifests" in tables:
                _seed_default_ingest_manifest(conn)
            if "metadata_field_configs" in tables:
                _seed_default_metadata_config(conn)
