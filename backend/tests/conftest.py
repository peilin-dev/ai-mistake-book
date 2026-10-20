import os
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ENV_TEST = Path(__file__).resolve().parent.parent / ".env.test"
if ENV_TEST.exists():
    for line in ENV_TEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from app.config import Settings, set_settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.deps import get_db  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    """The same object get_settings() returns during the test."""
    s = Settings(
        _env_file=None,
        DATABASE_URL=os.environ["TEST_DATABASE_URL"],
        STORAGE_DIR=str(tmp_path),
    )
    set_settings(s)
    yield s
    set_settings(None)

@pytest_asyncio.fixture
async def db(settings):
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db, settings):
    app = create_app()

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

