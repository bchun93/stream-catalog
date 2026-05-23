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

    for enum_name in _PG_ENUM_TYPES:
        conn.execute(text(f"DROP TYPE IF EXISTS {enum_name}"))


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
        with engine.begin() as conn:
            _upgrade_postgres_enums_to_varchar(conn)
            # Re-inspect; if enums remain, try adding values
            _ensure_pg_enum_values(conn)
