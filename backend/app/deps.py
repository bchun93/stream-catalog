from fastapi import HTTPException, Request


def require_db(request: Request) -> None:
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(
            status_code=503,
            detail=(
                "Database not configured. On Render, set DATABASE_URL to your "
                "Neon PostgreSQL URL (Dashboard → Environment)."
            ),
        )
