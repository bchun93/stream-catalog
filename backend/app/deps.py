from fastapi import Header, HTTPException, Request

from app.config import settings


def require_ingest_operator_token(x_ingest_token: str | None = Header(default=None)) -> None:
    token = (settings.ingest_operator_token or "").strip()
    if not token:
        return
    if x_ingest_token != token:
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
