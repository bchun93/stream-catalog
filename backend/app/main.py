import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.migrate import run_migrations
from app.routers import media_assets, metadata, titles
from app.seed import seed


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        run_migrations()
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("Database startup failed: %s", exc)
        raise
    if settings.seed_on_startup:
        try:
            seed()
        except Exception as exc:
            logger.warning("Startup seed skipped: %s", exc)
    yield


app = FastAPI(
    title="Stream Catalog API",
    description="Title management and media asset management for video streaming",
    version="1.0.0",
    lifespan=lifespan,
)

# Amplify, CloudFront, localhost, and Render previews.
_cors_regex = settings.cors_regex or r"https?://.*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


api = settings.api_prefix
app.include_router(metadata.router, prefix=api)
app.include_router(titles.router, prefix=api)
app.include_router(media_assets.router, prefix=api)


@app.get("/")
@app.head("/")
def root():
    return {"status": "ok", "service": "stream-catalog-api"}


@app.get("/health")
@app.head("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
@app.head("/ready")
def ready():
    """DB connectivity check for production debugging."""
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
