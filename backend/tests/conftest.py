import asyncio
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
from app.auth.wechat import WeChatAuthError, WxSession, get_wechat_client  # noqa: E402
from app.deps import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Assignment, Class_, Subject, Teacher  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Rebuild the schema once per session so model changes never leave stale columns."""

    async def _rebuild():
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_rebuild())


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


class FakeWeChatClient:
    def __init__(self) -> None:
        self.sessions: dict[str, WxSession] = {}

    async def code2session(self, code: str) -> WxSession:
        if code not in self.sessions:
            raise WeChatAuthError("invalid code")
        return self.sessions[code]


@pytest.fixture
def fake_wx():
    return FakeWeChatClient()


@pytest_asyncio.fixture
async def client(db, settings, fake_wx):
    app = create_app()

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_wechat_client] = lambda: fake_wx
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c



@pytest_asyncio.fixture
async def make_assignment(db):
    """Factory: teacher -> class -> assignment; callable repeatedly."""
    counter = 0

    async def _make(subject: Subject = Subject.math, **kwargs) -> Assignment:
        nonlocal counter
        counter += 1
        teacher = Teacher(unionid=f"u{counter}", mp_openid=f"o{counter}")
        db.add(teacher)
        await db.flush()
        cls = Class_(teacher_id=teacher.id, name=f"class{counter}", grade=5)
        db.add(cls)
        await db.flush()
        a = Assignment(class_id=cls.id, subject=subject, title=f"hw{counter}", **kwargs)
        db.add(a)
        await db.commit()
        return a

    return _make
