from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from railo_cloud.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    kwargs: dict = {"future": True}
    # Connection pooling only for non-SQLite (Postgres in production)
    if not settings.database_url.startswith("sqlite"):
        kwargs.update(
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return create_engine(settings.database_url, **kwargs)


@lru_cache(maxsize=1)
def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def get_session():
    factory = get_session_factory()
    return factory()
