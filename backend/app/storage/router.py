import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.storage.base import get_storage
from app.storage.local import LocalStorage, is_safe_key

router = APIRouter(tags=["files"])


@router.get("/files/{key:path}")
async def download_file(
    key: str, expires: int, sig: str, storage: LocalStorage = Depends(get_storage)
):
    """Signed-URL download; the signature is the auth, so no Bearer token."""
    if not is_safe_key(key):
        raise HTTPException(status_code=400, detail="invalid key")
    if not storage.verify(key, expires, sig):
        raise HTTPException(status_code=403, detail="invalid or expired signature")
    try:
        data = await storage.get(key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found") from None
    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(content=data, media_type=media_type)