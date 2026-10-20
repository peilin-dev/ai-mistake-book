from pathlib import Path
from typing import Protocol

from app.config import get_settings


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes:
        """Raises FileNotFoundError for a missing key."""
        ...

    async def delete(self, key: str) -> None:
        """Deleting a missing key is a no-op."""
        ...

    def signed_url(self, key: str, expires_s: int = 600) -> str: ...


def get_storage() -> Storage:
    from app.storage.local import LocalStorage

    return LocalStorage(Path(get_settings().STORAGE_DIR))