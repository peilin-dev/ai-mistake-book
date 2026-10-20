import asyncio
import hashlib
import hmac
import time
from pathlib import Path

from app.config import get_settings


def is_safe_key(key: str) -> bool:
    return bool(key) and not key.startswith("/") and ".." not in key and "\\" not in key and ":" not in key


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if not is_safe_key(key):
            raise ValueError(f"unsafe storage key: {key!r}")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"unsafe storage key: {key!r}")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)

    @staticmethod
    def _sign(key: str, expires: int) -> str:
        secret = get_settings().JWT_SECRET.encode()
        return hmac.new(secret, f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()

    def signed_url(self, key: str, expires_s: int = 600) -> str:
        expires = int(time.time()) + expires_s
        return f"/api/files/{key}?expires={expires}&sig={self._sign(key, expires)}"

    def verify(self, key: str, expires: int, sig: str) -> bool:
        return expires >= time.time() and hmac.compare_digest(self._sign(key, expires), sig)