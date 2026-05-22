import logging

from sqlalchemy import inspect, text

from app.database import engine
from app.models.media_asset import AssetStatus, AssetType
from app.models.title import TitleStatus, TitleType

logger = logging.getLogger(__name__)

_NEW_COLUMNS = [
    ("release_year", "INTEGER"),
    ("licensor", "VARCHAR(255)"),
    ("studio", "VARCHAR(500)"),
    ("cast", "TEXT"),
    ("crew", "TEXT"),
    ("external_id", "VARCHAR(64)"),
    ("metadata_source", "VARCHAR(32)"),
    ("poster_url", "VARCHAR(1024)"),
]

_MEDIA_ASSET_COLUMNS = [
    ("metadata_json", "TEXT"),
]

# Legacy Postgres enum type names (from early deploys).
_PG_ENUM_TYPES = (
    "assettype",
    "assetstatus",
    "titletype",
    "titlestatus",
)

# Columns that must be VARCHAR to match SQLAlchemy native_enum=False + SQLite locally.
_PG_ENUM_COLUMNS: tuple[tuple[str, str, int], ...] = (
    ("media_assets", "asset_type", 32),
    ("media_assets", "status", 32),
    ("titles", "title_type", 32),
    ("titles", "status", 32),
)


def _quote_ident(name: str) -> str:
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def _is_postgres_enum_column(col: dict) -> bool:
    col_type = col.get("type")
    type_str = repr(col_type).upper()
    if "ENUM" in type_str:
        return True
    if hasattr(col_type, "enums") or hasattr(col_type, "name"):
        return True
    return False


def _upgrade_postgres_enums_to_varchar(conn) -> None:
    """Convert legacy native PG enums to VARCHAR so all AssetType values work."""
    inspector = inspect(conn)
    for table, column, varchar_len in _PG_ENUM_COLUMNS:
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"]: c for c in inspector.get_columns(table)}
        if column not in cols:
            continue
        if not _is_postgres_enum_column(cols[column]):
            continue

        col_ident = _quote_ident(column)
        table_ident = _quote_ident(table)
        logger.info("Migrating %s.%s from PG enum to VARCHAR(%s)", table, column, varchar_len)

        conn.execute(
            text(
                f"ALTER TABLE {table_ident} "
                f"ALTER COLUMN {col_ident} TYPE VARCHAR({varchar_len}) "
                f"USING {col_ident}::text"
            )
        )
        conn.execute(
            text(f"UPDATE {table_ident} SET {col_ident} = LOWER({col_ident})")
        )

    for enum_name in _PG_ENUM_TYPES:
        conn.execute(text(f"DROP TYPE IF EXISTS {enum_name}"))


def _ensure_pg_enum_values(conn) -> None:
    """If enum columns still exist, add missing labels (fallback)."""
    additions = {
        "assettype": [e.name for e in AssetType],
        "assetstatus": [e.name for e in AssetStatus],
        "titletype": [e.name for e in TitleType],
        "titlestatus": [e.name for e in TitleStatus],
    }
    for type_name, labels in additions.items():
        for label in labels:
            try:
                conn.execute(
                    text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{label}'")
                )
            except Exception:
                pass


def run_migrations() -> None:
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
        with engine.begin() as conn:
            _upgrade_postgres_enums_to_varchar(conn)
            # Re-inspect; if enums remain, try adding values
            _ensure_pg_enum_values(conn)
