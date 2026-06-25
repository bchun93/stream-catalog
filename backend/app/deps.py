import secrets

from fastapi import Header, HTTPException, Request

from app.config import settings


def _token_matches(provided: str | None, expected: str) -> bool:
    supplied = (provided or "").strip()
    if not supplied or len(supplied) != len(expected):
        return False
    return secrets.compare_digest(supplied, expected)


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    """When ADMIN_API_KEY is set, mutating routes require X-Admin-Token."""
    expected = (settings.admin_api_key or "").strip()
    if not expected:
        return
    if not _token_matches(x_admin_token, expected):
        raise HTTPException(
            status_code=403,
            detail="Missing or invalid admin token.",
        )


def require_ingest_operator_token(x_ingest_token: str | None = Header(default=None)) -> None:
    token = (settings.ingest_operator_token or "").strip()
    if not token:
        return
    if not _token_matches(x_ingest_token, token):
        raise HTTPException(
            status_code=403,
            detail="Missing or invalid ingest operator token.",
        )


def require_db(request: Request) -> None:
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(
            status_code=503,
            detail=(
                "Database not configured. On Render, set DATABASE_URL to your "
                "Neon PostgreSQL URL (Dashboard → Environment)."
            ),
        )
