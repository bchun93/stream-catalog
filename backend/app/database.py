from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

url = make_url(settings.database_url)
_connect_args: dict = {}

if url.drivername.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
elif url.drivername.startswith("postgresql"):
    _connect_args["sslmode"] = "require"

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
