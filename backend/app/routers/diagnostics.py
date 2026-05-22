"""Public diagnostics — what the running API actually sees (not dashboard copy)."""

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import settings
from app.database import SessionLocal

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


def _mask_host(host: str | None) -> str | None:
    if not host:
        return None
    if host.startswith("ep-"):
        return host.split(".")[0] + ".neon.tech"
    return host[:24] + ("…" if len(host) > 24 else "")


def _hints(*, db_ready: bool, neon_pooler: bool, migration_error: str | None, tmdb: bool) -> list[str]:
    hints: list[str] = []
    if not db_ready:
        hints.append(
            "Database not ready on this Render instance. Check Render Logs for startup errors."
        )
        if neon_pooler:
            hints.append(
                "DATABASE_URL uses Neon pooler (-pooler host). Use the DIRECT connection "
                "string from Neon → Connect (not Connection pooling)."
            )
        if migration_error:
            hints.append(f"Last migration error: {migration_error[:200]}")
    if not tmdb:
        hints.append("TMDB_API_KEY is missing or still a placeholder on Render.")
    hints.append(
        "Amplify VITE_API_URL is baked in at build time — changing it in Amplify requires a full redeploy."
    )
    return hints


@router.get("")
def get_diagnostics(request: Request):
    url = make_url(settings.database_url)
    host = url.host or ""
    neon_pooler = "pooler" in host
    db_ready = bool(getattr(request.app.state, "db_ready", False))
    migration_error = getattr(request.app.state, "migration_error", None)

    titles_count: int | None = None
    titles_error: str | None = None
    if db_ready:
        try:
            with SessionLocal() as db:
                titles_count = db.execute(text("SELECT COUNT(*) FROM titles")).scalar()
        except Exception as exc:
            titles_error = str(exc)

    return {
        "status": "ok",
        "db_ready": db_ready,
        "database_driver": url.drivername,
        "database_host": _mask_host(host),
        "neon_pooler": neon_pooler,
        "migration_error": migration_error,
        "tmdb_configured": settings.tmdb_configured,
        "titles_count": titles_count,
        "titles_error": titles_error,
        "hints": _hints(
            db_ready=db_ready,
            neon_pooler=neon_pooler,
            migration_error=migration_error,
            tmdb=settings.tmdb_configured,
        ),
    }
