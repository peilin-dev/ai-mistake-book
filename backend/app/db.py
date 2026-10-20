from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_sessionmaker = None


def make_engine(url: str) -> AsyncEngine:
    """READ COMMITTED for the API and the worker: reads after a row lock must see other commits."""
    return create_async_engine(url, pool_pre_ping=True, isolation_level="READ COMMITTED")


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        _engine = make_engine(get_settings().DATABASE_URL)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker
