from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import media_assets, titles
from app.seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_startup:
        seed()
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = settings.api_prefix
app.include_router(titles.router, prefix=api)
app.include_router(media_assets.router, prefix=api)


@app.get("/health")
def health():
    return {"status": "ok"}
