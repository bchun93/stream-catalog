"""Runtime repair for legacy Postgres enum values (EPISODE vs episode)."""

import logging

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def is_legacy_enum_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "among the defined enum values" in text
        or "invalid input value for enum" in text
        or ("enum name:" in text and "titletype" in text)
        or ("enum name:" in text and "assettype" in text)
        or ("enum name:" in text and "assetstatus" in text)
    )


def repair_legacy_enums() -> bool:
    """Lowercase legacy uppercase enum strings in place. Returns True on success."""
    from app.migrate import repair_legacy_enum_strings

    try:
        repair_legacy_enum_strings()
        return True
    except Exception:
        logger.exception("repair_legacy_enums failed")
        return False


def retry_after_enum_repair(db, operation):
    """Run a DB operation; repair legacy enum rows and retry once on enum mismatch."""
    try:
        return operation()
    except (LookupError, ValueError, SQLAlchemyError) as exc:
        if not is_legacy_enum_error(exc):
            raise
        logger.warning("Legacy enum values detected — repairing and retrying: %s", exc)
        db.rollback()
        if not repair_legacy_enums():
            raise
        return operation()
