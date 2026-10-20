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
from app.db import Base, make_engine  # noqa: E402
from app.auth.wechat import WeChatAuthError, WxSession, get_wechat_client  # noqa: E402
from app.auth.tokens import issue_token  # noqa: E402
from app.deps import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Assignment, Class_, Subject, Teacher  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Rebuild the schema once per session so model changes never leave stale columns."""

    async def _rebuild():
        engine = make_engine(os.environ["TEST_DATABASE_URL"])
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
    engine = make_engine(settings.DATABASE_URL)
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


@pytest.fixture
def app(db, fake_wx, settings):
    app = create_app()

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_wechat_client] = lambda: fake_wx
    return app


@pytest_asyncio.fixture
async def client(app):
    """Unauthenticated client."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def client_for(app):
    """Factory: a fresh client authenticated as the given teacher."""
    clients: list[httpx.AsyncClient] = []

    def _make(teacher: Teacher) -> httpx.AsyncClient:
        c = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {issue_token(teacher.id)}"},
        )
        clients.append(c)
        return c

    yield _make
    for c in clients:
        await c.aclose()


@pytest_asyncio.fixture
async def make_teacher(db):
    """Factory: a committed Teacher with unique ids."""
    counter = 0

    async def _make() -> Teacher:
        nonlocal counter
        counter += 1
        t = Teacher(unionid=f"ut{counter}", mp_openid=f"ot{counter}")
        db.add(t)
        await db.commit()
        return t

    return _make


@pytest_asyncio.fixture
async def teacher(make_teacher) -> Teacher:
    return await make_teacher()


@pytest_asyncio.fixture
async def auth_client(client_for, teacher):
    """A client logged in as `teacher`; `client` stays unauthenticated."""
    return client_for(teacher)


@pytest_asyncio.fixture
async def my_class(db, teacher) -> Class_:
    c = Class_(teacher_id=teacher.id, name="五(2)班", grade=5)
    db.add(c)
    await db.commit()
    return c


@pytest_asyncio.fixture
async def other_teacher_class(db, make_teacher) -> Class_:
    other = await make_teacher()
    c = Class_(teacher_id=other.id, name="别人的班", grade=5)
    db.add(c)
    await db.commit()
    return c


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


# --- Task 6 fixtures ---
import io  # noqa: E402

from PIL import Image  # noqa: E402

from app.assignments.router import get_enqueuer  # noqa: E402
from app.storage.base import get_storage  # noqa: E402
from app.storage.local import LocalStorage  # noqa: E402


@pytest_asyncio.fixture
async def my_assignment(db, my_class) -> Assignment:
    a = Assignment(class_id=my_class.id, subject=Subject.math, title="math hw")
    db.add(a)
    await db.commit()
    return a


@pytest.fixture
def make_jpeg():
    """Factory: valid JPEGs whose bytes differ per n."""

    def _make(n: int = 0) -> bytes:
        img = Image.new("RGB", (16, 16), (n * 37 % 256, n * 91 % 256, (n * 53 + 10) % 256))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    return _make


@pytest.fixture
def jpeg_bytes(make_jpeg) -> bytes:
    return make_jpeg(0)


class _Calls(list):
    """List of enqueued page_ids; `.retries` holds the matching retry arguments."""

    def __init__(self) -> None:
        super().__init__()
        self.retries: list[int] = []


@pytest.fixture
def enqueued(app) -> list[int]:
    """page_ids received by the (overridden) enqueue dependency."""
    calls: _Calls = _Calls()

    async def _enqueue(page_id: int, retry: int = 0) -> None:
        calls.append(page_id)
        calls.retries.append(retry)

    app.dependency_overrides[get_enqueuer] = lambda: _enqueue
    return calls


@pytest.fixture
def storage(app, settings) -> LocalStorage:
    s = LocalStorage(Path(settings.STORAGE_DIR))
    app.dependency_overrides[get_storage] = lambda: s
    return s

# --- Task 8 fixtures ---
import yaml as _yaml  # noqa: E402


@pytest.fixture
def sample_yaml() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "knowledge" / "math_primary_sample.yaml"


@pytest.fixture
def count_nodes():
    """Counts every node (inner and leaf) in a knowledge YAML file."""

    def _count(path: Path) -> int:
        def walk(nodes) -> int:
            return sum(1 + walk(n.get("children") or []) for n in nodes)

        doc = _yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return walk(doc["nodes"])

    return _count


# --- Task 7 fixtures ---
import json as _json  # noqa: E402


class MockTransport(httpx.AsyncBaseTransport):
    """Records requests and replays canned responses (last one repeats)."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._replies: list[httpx.Response | Exception] = []

    def reply(self, body: dict | str, status: int = 200) -> None:
        content = body if isinstance(body, str) else _json.dumps(body)
        self._replies.append(httpx.Response(status, content=content.encode()))

    def fail(self, exc: Exception) -> None:
        self._replies.append(exc)

    @property
    def last_body(self) -> dict:
        return _json.loads(self.requests[-1].content)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.requests.append(request)
        item = self._replies[min(len(self.requests), len(self._replies)) - 1]
        if isinstance(item, Exception):
            raise item
        return httpx.Response(item.status_code, content=item.content, request=request)


@pytest.fixture
def mock_transport() -> MockTransport:
    return MockTransport()

# --- Task 11 fixtures ---
from app.ai.fake import FakeModel  # noqa: E402
from app.grading.answer_key import get_answer_key_model  # noqa: E402

KEY_QUESTIONS = [
    {"question_no": "1", "answer": "7", "max_score": 2, "is_subjective": False},
    {"question_no": "2", "answer": "12", "max_score": 4, "is_subjective": False},
]


@pytest.fixture
def install_answer_key_model(app):
    """Factory: installs a FakeModel replaying `responses` as the answer-key model."""

    def _install(responses: list) -> FakeModel:
        model = FakeModel(responses)
        app.dependency_overrides[get_answer_key_model] = lambda: model
        return model

    return _install


@pytest.fixture
def fake_model_answer_key(install_answer_key_model) -> FakeModel:
    return install_answer_key_model([{"questions": KEY_QUESTIONS}])


# --- Task 10 fixtures ---
from app.models import AnswerItem, AnswerKeyStatus, Page, PageStatus, Student  # noqa: E402


def q(**kw) -> dict:
    """One question as the grading model returns it (spec 7.1)."""
    item = {
        "no": "1",
        "question_text": "3 + 4 = ?",
        "student_answer": "7",
        "correct_answer": "7",
        "is_subjective": False,
        "is_correct": True,
        "score": 2,
        "max_score": 2,
        "confidence": 0.95,
        "bbox": [0.1, 0.1, 0.9, 0.2],
        "knowledge_point_id": None,
        "error_reason": None,
    }
    item.update(kw)
    return item


def graded(student_name: str | None = None, questions: list[dict] | None = None) -> dict:
    return {"student_name": student_name, "questions": questions or []}


def paper_jpeg(width: int = 600, height: int = 800, seed: int = 0) -> bytes:
    img = Image.new("RGB", (width, height), (255, 255, (250 + seed) % 256))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest_asyncio.fixture
async def make_page(db, storage, my_assignment, teacher):
    """Factory: a queued Page of my_assignment whose JPEG is really stored."""

    async def _make(seq: int) -> Page:
        data = paper_jpeg(seed=seq)
        page = Page(assignment_id=my_assignment.id, seq=seq, image_key="",
                    image_sha256=f"sha{seq}", status=PageStatus.queued)
        db.add(page)
        await db.flush()
        page.image_key = f"originals/{teacher.id}/{my_assignment.id}/{page.id}.jpg"
        await storage.put(page.image_key, data, "image/jpeg")
        await db.commit()
        return page

    return _make


@pytest_asyncio.fixture
async def uploaded_page(make_page) -> Page:
    return await make_page(1)


@pytest_asyncio.fixture
async def two_uploaded_pages(make_page) -> list[Page]:
    return [await make_page(1), await make_page(2)]


@pytest_asyncio.fixture
async def roster_zhangsan(db, my_class) -> Student:
    s = Student(class_id=my_class.id, name="张三")
    db.add(s)
    await db.commit()
    return s


@pytest_asyncio.fixture
async def confirmed_key_q1_q2(db, my_assignment) -> list[AnswerItem]:
    my_assignment.answer_key_status = AnswerKeyStatus.confirmed
    items = [
        AnswerItem(assignment_id=my_assignment.id, question_no="1", answer="7", max_score=2),
        AnswerItem(assignment_id=my_assignment.id, question_no="2", answer="12", max_score=4),
    ]
    db.add_all(items)
    await db.commit()
    return items


# --- Task 12 fixtures ---
from types import SimpleNamespace  # noqa: E402

from app.models import QuestionResult, Submission  # noqa: E402


def make_result(page_id: int, submission_id: int | None, no: str, **kw) -> QuestionResult:
    fields = dict(question_no=no, question_text="t", student_answer="a", correct_answer="a",
                  answer_verified=True, is_correct=True, score=2, max_score=2, confidence=0.95,
                  needs_review=False, reviewed=False, crop_key=None)
    fields.update(kw)
    return QuestionResult(page_id=page_id, submission_id=submission_id, **fields)


@pytest_asyncio.fixture
async def make_done_page(db, storage, my_assignment, teacher):
    """Factory: a done Page of my_assignment with a stored image."""

    async def _make(seq: int, student_id: int | None = None, name: str | None = None) -> Page:
        page = Page(assignment_id=my_assignment.id, seq=seq, image_key="", image_sha256=f"d{seq}",
                    status=PageStatus.done, student_id=student_id, recognized_name=name)
        db.add(page)
        await db.flush()
        page.image_key = f"originals/{teacher.id}/{my_assignment.id}/{page.id}.jpg"
        await storage.put(page.image_key, paper_jpeg(seed=seq), "image/jpeg")
        await db.commit()
        return page

    return _make


@pytest_asyncio.fixture
async def graded_submission(db, my_assignment, roster_zhangsan, make_done_page):
    """Submission with q1 judged correct (2/2) and q2 wrong (0/4); total 2."""
    page = await make_done_page(10, roster_zhangsan.id, "张三")
    sub = Submission(assignment_id=my_assignment.id, student_id=roster_zhangsan.id,
                     total_score=2, needs_review_count=0)
    db.add(sub)
    await db.flush()
    qs = [make_result(page.id, sub.id, "1"),
          make_result(page.id, sub.id, "2", is_correct=False, score=0, max_score=4)]
    db.add_all(qs)
    await db.commit()
    return SimpleNamespace(id=sub.id, student_id=roster_zhangsan.id, total_score=2,
                           questions=qs, page=page)


@pytest_asyncio.fixture
async def unmatched_page(db, make_done_page) -> Page:
    page = await make_done_page(1, None, "张小三")
    db.add_all([make_result(page.id, None, "1", needs_review=True),
                make_result(page.id, None, "2", needs_review=True, is_correct=False, score=0, max_score=4)])
    await db.commit()
    return page


@pytest_asyncio.fixture
async def other_class_student(db, other_teacher_class) -> Student:
    s = Student(class_id=other_teacher_class.id, name="外班生")
    db.add(s)
    await db.commit()
    return s


# --- Task 13 fixtures ---
from datetime import datetime, timedelta, timezone  # noqa: E402


def utcnow() -> datetime:
    """Naive UTC, matching the created_at columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def storage_exists(storage, key: str) -> bool:
    try:
        await storage.get(key)
    except FileNotFoundError:
        return False
    return True


@pytest_asyncio.fixture
async def page_factory(db, storage, make_assignment):
    """Factory: a Page (original stored) created `created_days_ago` days ago.

    Each call uses its own teacher/class/assignment. With with_crop=True the page
    also has one QuestionResult whose crop is stored.
    """
    counter = 0

    async def _make(created_days_ago: float, with_crop: bool = False, **page_kw) -> SimpleNamespace:
        nonlocal counter
        counter += 1
        assignment = await make_assignment()
        page_kw.setdefault("status", PageStatus.done)
        page = Page(assignment_id=assignment.id, seq=1, image_key="", image_sha256=f"pf{counter}",
                    **page_kw)
        db.add(page)
        await db.flush()
        page.created_at = utcnow() - timedelta(days=created_days_ago)
        page.image_key = f"originals/pf/{page.id}.jpg"
        await storage.put(page.image_key, paper_jpeg(seed=counter), "image/jpeg")
        crop_keys: list[str] = []
        if with_crop:
            key = f"crops/pf/{page.id}-1.jpg"
            await storage.put(key, paper_jpeg(100, 100, counter), "image/jpeg")
            db.add(make_result(page.id, None, "1", crop_key=key))
            crop_keys.append(key)
        await db.commit()
        return SimpleNamespace(id=page.id, image_key=page.image_key, crop_keys=crop_keys)

    return _make




# --- M3 Task 2 fixtures ---
import hashlib as _hashlib  # noqa: E402

from sqlalchemy import func as _func, select as _select  # noqa: E402


async def count_results(db, page_id: int) -> int:
    return (await db.execute(
        _select(_func.count()).select_from(QuestionResult).where(QuestionResult.page_id == page_id)
    )).scalar_one()


@pytest_asyncio.fixture
async def failed_page_factory(db, storage, my_assignment, teacher):
    """Factory: a failed Page of my_assignment (original stored), optionally with old results."""
    seq_counter = 0

    async def _make(reason: str = "unreadable", with_results: bool = False) -> Page:
        nonlocal seq_counter
        seq_counter += 1
        data = paper_jpeg(seed=100 + seq_counter)
        page = Page(assignment_id=my_assignment.id, seq=seq_counter, image_key="",
                    image_sha256=_hashlib.sha256(data).hexdigest(),
                    status=PageStatus.failed, fail_reason=reason)
        db.add(page)
        await db.flush()
        page.image_key = f"originals/{teacher.id}/{my_assignment.id}/{page.id}.jpg"
        await storage.put(page.image_key, data, "image/jpeg")
        if with_results:
            student = Student(class_id=my_assignment.class_id, name="张三")
            db.add(student)
            await db.flush()
            sub = Submission(assignment_id=my_assignment.id, student_id=student.id, total_score=2)
            db.add(sub)
            await db.flush()
            page.student_id, page.recognized_name = student.id, "张三"
            for no in ("1", "2"):
                key = f"crops/{teacher.id}/{my_assignment.id}/old-{page.id}-{no}.jpg"
                await storage.put(key, paper_jpeg(50, 50), "image/jpeg")
                db.add(make_result(page.id, sub.id, no, crop_key=key))
        await db.commit()
        return page

    return _make


@pytest_asyncio.fixture
async def failed_page(failed_page_factory) -> Page:
    return await failed_page_factory("unreadable")


@pytest_asyncio.fixture
async def failed_page_with_results(failed_page_factory) -> Page:
    return await failed_page_factory("unreadable", with_results=True)


@pytest_asyncio.fixture
async def second_page_bytes(db, storage, my_assignment, teacher, failed_page) -> bytes:
    """Original bytes of another page of the same assignment."""
    data = paper_jpeg(seed=200)
    page = Page(assignment_id=my_assignment.id, seq=failed_page.seq + 1, image_key="",
                image_sha256=_hashlib.sha256(data).hexdigest(), status=PageStatus.done)
    db.add(page)
    await db.flush()
    page.image_key = f"originals/{teacher.id}/{my_assignment.id}/{page.id}.jpg"
    await storage.put(page.image_key, data, "image/jpeg")
    await db.commit()
    return data


@pytest_asyncio.fixture
async def other_teacher_failed_page(db, make_assignment) -> Page:
    a = await make_assignment()
    page = Page(assignment_id=a.id, seq=1, image_key="originals/x/y/1.jpg", image_sha256="foreign",
                status=PageStatus.failed, fail_reason="unreadable")
    db.add(page)
    await db.commit()
    return page
