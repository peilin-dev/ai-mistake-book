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

    async def ttl(self, key: str) -> int: ...


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
        n = await self._r.incr(key)
        if n == 1:
            await self._r.expire(key, ttl_s)
        return int(n)

    async def ttl(self, key: str) -> int:
        n = await self._r.ttl(key)
        return max(int(n), 0)


_store: RedisTicketStore | None = None


def get_ticket_store() -> TicketStore:
    global _store
    if _store is None:
        client = aioredis.from_url(get_settings().REDIS_URL, decode_responses=True)
        _store = RedisTicketStore(client)
    return _store
