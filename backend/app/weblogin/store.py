import json
from typing import Protocol

import redis.asyncio as aioredis

from app.auth.wechat import KeyValueCache
from app.config import get_settings


class TicketStore(KeyValueCache, Protocol):
    async def get_json(self, key: str) -> dict | None: ...

    async def set_json(self, key: str, value: dict, ttl_s: int) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def incr(self, key: str, ttl_s: int) -> int: ...

    async def take_json(self, key: str) -> dict | None:
        """Atomically read and delete a JSON value (single-use secrets such as captchas)."""
        ...

    async def ttl(self, key: str) -> int: ...

    async def transition(
        self,
        key: str,
        expect_status: str,
        new_status: str,
        new_teacher_id: int | None = None,
        expect_teacher_id: int | None = None,
    ) -> str:
        """Atomic compare-and-set on a ticket, keeping its TTL and never recreating it.

        Returns "ok", "missing" (no such ticket) or "conflict" (status/teacher mismatch).
        """
        ...

    async def take_confirmed(self, key: str, poll_key: str) -> tuple[str, dict | None]:
        """Atomically hand out and delete a confirmed ticket.

        Returns ("ok", data) once; otherwise ("missing" | "badkey" | "notready", None)
        and the ticket is left untouched.
        """
        ...


# Lua (EVAL works on Redis 3.2 as well as 7; no GETDEL / KEEPTTL needed).
_TRANSITION_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 'missing' end
local d = cjson.decode(raw)
if d.status ~= ARGV[1] then return 'conflict' end
if ARGV[4] ~= '' and tostring(d.teacher_id) ~= ARGV[4] then return 'conflict' end
local pttl = redis.call('PTTL', KEYS[1])
if pttl <= 0 then return 'missing' end
d.status = ARGV[2]
if ARGV[3] ~= '' then d.teacher_id = tonumber(ARGV[3]) end
redis.call('SET', KEYS[1], cjson.encode(d), 'PX', pttl)
return 'ok'
"""

_TAKE_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 'missing' end
local d = cjson.decode(raw)
if d.poll_key ~= ARGV[1] then return 'badkey' end
if d.status ~= 'confirmed' then return 'notready' end
redis.call('DEL', KEYS[1])
return raw
"""


# INCR and (re)arm the expiry in one step, so a counter can never be left without a TTL.
_INCR_LUA = """
local n = redis.call('INCR', KEYS[1])
if n == 1 or redis.call('TTL', KEYS[1]) < 0 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return n
"""

_TAKE_ANY_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then return false end
redis.call('DEL', KEYS[1])
return raw
"""


class RedisTicketStore:
    def __init__(self, client: aioredis.Redis) -> None:
        self._r = client

    async def get(self, key: str) -> str | None:
        return await self._r.get(key)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        await self._r.set(key, value, ex=ttl_s)

    async def get_json(self, key: str) -> dict | None:
        raw = await self._r.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: dict, ttl_s: int) -> None:
        await self._r.set(key, json.dumps(value), ex=ttl_s)

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def incr(self, key: str, ttl_s: int) -> int:
        return int(await self._r.eval(_INCR_LUA, 1, key, str(ttl_s)))

    async def take_json(self, key: str) -> dict | None:
        raw = await self._r.eval(_TAKE_ANY_LUA, 1, key)
        return json.loads(raw) if raw else None

    async def ttl(self, key: str) -> int:
        n = await self._r.ttl(key)
        return max(int(n), 0)

    async def transition(
        self,
        key: str,
        expect_status: str,
        new_status: str,
        new_teacher_id: int | None = None,
        expect_teacher_id: int | None = None,
    ) -> str:
        res = await self._r.eval(
            _TRANSITION_LUA,
            1,
            key,
            expect_status,
            new_status,
            "" if new_teacher_id is None else str(new_teacher_id),
            "" if expect_teacher_id is None else str(expect_teacher_id),
        )
        return str(res)

    async def take_confirmed(self, key: str, poll_key: str) -> tuple[str, dict | None]:
        res = str(await self._r.eval(_TAKE_LUA, 1, key, poll_key))
        if res.startswith("{"):
            return "ok", json.loads(res)
        return res, None


_store: RedisTicketStore | None = None


def get_ticket_store() -> TicketStore:
    global _store
    if _store is None:
        client = aioredis.from_url(get_settings().REDIS_URL, decode_responses=True)
        _store = RedisTicketStore(client)
    return _store
