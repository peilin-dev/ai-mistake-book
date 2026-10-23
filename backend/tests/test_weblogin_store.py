import asyncio
import json
import uuid

import pytest
import redis.asyncio as aioredis

from app.config import get_settings
from app.weblogin.store import RedisTicketStore


@pytest.fixture
async def store():
    r = aioredis.from_url(get_settings().REDIS_URL, decode_responses=True)
    try:
        await r.ping()
    except Exception:
        await r.aclose()
        pytest.skip("local Redis not reachable")
    s = RedisTicketStore(r)
    prefix = f"test-weblogin:{uuid.uuid4().hex}:"
    yield s, prefix
    async for k in r.scan_iter(match=f"{prefix}*"):
        await r.delete(k)
    await r.aclose()


def _ticket(status="pending", teacher_id=None):
    return {"poll_key": "pk", "pair_code": "1234", "status": status, "teacher_id": teacher_id}


async def test_transition_cas_keeps_ttl_and_never_recreates(store):
    s, p = store
    k = p + "a"
    assert await s.transition(k, "pending", "scanned", 7) == "missing"
    assert await s.get(k) is None
    await s.set_json(k, _ticket(), 100)
    assert await s.transition(k, "pending", "scanned", 7) == "ok"
    assert await s.transition(k, "pending", "scanned", 8) == "conflict"
    assert (await s.get_json(k))["teacher_id"] == 7
    assert 90 <= await s.ttl(k) <= 100
    assert await s.transition(k, "scanned", "confirmed", expect_teacher_id=8) == "conflict"
    assert await s.transition(k, "scanned", "confirmed", expect_teacher_id=7) == "ok"
    assert (await s.get_json(k))["status"] == "confirmed"


async def test_concurrent_scans_only_one_wins(store):
    s, p = store
    k = p + "b"
    await s.set_json(k, _ticket(), 100)
    res = await asyncio.gather(*(s.transition(k, "pending", "scanned", i) for i in range(1, 9)))
    assert sorted(res) == ["conflict"] * 7 + ["ok"]


async def test_take_confirmed_is_atomic_single_handout(store):
    s, p = store
    k = p + "c"
    await s.set_json(k, _ticket("confirmed", 3), 100)
    assert await s.take_confirmed(k, "wrong") == ("badkey", None)
    res = await asyncio.gather(*(s.take_confirmed(k, "pk") for _ in range(6)))
    assert [c for c, _ in res].count("ok") == 1
    assert all(c == "missing" for c, _ in res if c != "ok")
    assert await s.get(k) is None
    # a late transition cannot resurrect it
    assert await s.transition(k, "scanned", "confirmed", expect_teacher_id=3) == "missing"
    assert await s.get(k) is None


async def test_take_requires_confirmed(store):
    s, p = store
    k = p + "d"
    await s.set_json(k, _ticket("scanned", 3), 100)
    assert await s.take_confirmed(k, "pk") == ("notready", None)
    assert json.loads(await s.get(k))["status"] == "scanned"