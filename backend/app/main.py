import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.migrate import run_migrations
from app.routers import media_assets, metadata, titles
from app.seed import seed


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_migrations()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = settings.api_prefix
app.include_router(metadata.router, prefix=api)
app.include_router(titles.router, prefix=api)
app.include_router(media_assets.router, prefix=api)


@app.get("/health")
def health():
    return {"status": "ok"}
