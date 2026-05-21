from sqlalchemy import inspect, text

from app.database import engine

_NEW_COLUMNS = [
    ("release_year", "INTEGER"),
    ("licensor", "VARCHAR(255)"),
    ("studio", "VARCHAR(500)"),
    ("cast", "TEXT"),
    ("crew", "TEXT"),
    ("external_id", "VARCHAR(64)"),
    ("metadata_source", "VARCHAR(32)"),
]


def _quote_ident(name: str) -> str:
    """Quote identifiers so reserved words (e.g. cast) work on PostgreSQL."""
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def run_migrations() -> None:
    inspector = inspect(engine)
    if "titles" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("titles")}
    with engine.begin() as conn:
        for name, col_type in _NEW_COLUMNS:
            if name not in existing:
                col = _quote_ident(name)
                conn.execute(
                    text(f"ALTER TABLE titles ADD COLUMN {col} {col_type}")
                )
