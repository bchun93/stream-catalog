import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import Base, SessionLocal, check_database, engine
from app.middleware.cors import EchoOriginCORSMiddleware
from app.migrate import run_migrations
from app.routers import (
    artwork_ai,
    diagnostics,
    ingest,
    media_assets,
    metadata,
    metadata_config,
    storage,
    titles,
)
from app.seed import seed


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_ready = False
    app.state.migration_error = None
    if os.environ.get("PORT") and not os.environ.get("DATABASE_URL"):
        logger.warning(
            "DATABASE_URL is not set on Render — titles will not persist. "
            "Add your Neon PostgreSQL URL under Environment."
        )
    try:
        Base.metadata.create_all(bind=engine)
        try:
            run_migrations()
        except Exception as exc:
            app.state.migration_error = str(exc)
            logger.exception("Migration failed (continuing if DB connects): %s", exc)
        check_database()
        app.state.db_ready = True
        logger.info("Database ready (%s)", engine.url.drivername)
    except Exception as exc:
        logger.exception("Database startup failed (metadata routes still work): %s", exc)

    if settings.tmdb_configured:
        logger.info("TMDB API key configured")
    else:
        logger.warning(
            "TMDB_API_KEY is not set on this service — metadata search and import will fail"
        )

    if app.state.db_ready and settings.seed_on_startup:
        try:
            seed()
        except Exception as exc:
            logger.warning("Startup seed skipped: %s", exc)
    yield


app = FastAPI(
    title="Relay API",
    description="Title management and media asset management for video streaming",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_regex or r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
app.add_middleware(EchoOriginCORSMiddleware)


def _cors_json(request: Request, status_code: int, detail: str) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content={"detail": detail})
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return _cors_json(request, exc.status_code, str(exc.detail))


@app.exception_handler(ResponseValidationError)
async def response_validation_handler(request: Request, exc: ResponseValidationError):
    logger.exception("Response validation failed on %s %s", request.method, request.url.path)
    return _cors_json(
        request,
        500,
        "API response validation failed. Redeploy the latest API build from main.",
    )


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    if isinstance(exc, SQLAlchemyError):
        return _cors_json(
            request,
            503,
            "Database error. Verify DATABASE_URL on Render (Neon) and redeploy.",
        )
    return _cors_json(request, 500, str(exc))


api = settings.api_prefix
app.include_router(diagnostics.router, prefix=api)
app.include_router(ingest.router, prefix=api)
app.include_router(storage.router, prefix=api)
app.include_router(metadata.router, prefix=api)
app.include_router(metadata_config.router, prefix=api)
app.include_router(titles.router, prefix=api)
app.include_router(artwork_ai.router, prefix=api)
app.include_router(media_assets.router, prefix=api)


@app.get("/")
@app.head("/")
def root():
    return {"status": "ok", "service": "stream-catalog-api"}


@app.get("/health")
@app.head("/health")
def health():
    return {"status": "ok", "tmdb_configured": settings.tmdb_configured}


@app.get("/ready")
@app.head("/ready")
def ready(request: Request):
    if not getattr(app.state, "db_ready", False):
        migration_error = getattr(app.state, "migration_error", None)
        detail = (
            "Database not ready. Set DATABASE_URL on Render to your Neon connection string."
        )
        if migration_error:
            detail = f"{detail} Migration error: {migration_error[:240]}"
        return _cors_json(request, 503, detail)
    try:
        check_database()
    except Exception as exc:
        return _cors_json(request, 503, f"Database unreachable: {exc}")
    return {"status": "ok", "database": "connected"}
