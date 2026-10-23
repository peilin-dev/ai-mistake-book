import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings

JSCODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WXACODE_URL = "https://api.weixin.qq.com/wxa/getwxacodeunlimit"
ACCESS_TOKEN_KEY = "wx:access_token"


def _error_json(resp: httpx.Response) -> dict | None:
    """WeChat answers errors with JSON (sometimes labelled text/plain) and success with an image."""
    if resp.headers.get("content-type", "").startswith("image/"):
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    if isinstance(data, dict) and data.get("errcode"):
        return data
    return None


class WeChatAuthError(Exception):
    pass


@dataclass(frozen=True)
class WxSession:
    openid: str
    unionid: str | None = None


class WeChatQrError(Exception):
    pass


class KeyValueCache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_s: int) -> None: ...

    async def delete(self, key: str) -> None: ...


class _MemoryCache:
    """Per-instance fallback when no shared cache is injected."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}

    async def get(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None or item[1] <= time.monotonic():
            self._data.pop(key, None)
            return None
        return item[0]

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        self._data[key] = (value, time.monotonic() + ttl_s)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)


class WeChatClient(Protocol):
    async def code2session(self, code: str) -> WxSession: ...

    async def wxacode(self, scene: str) -> bytes: ...


class HttpWeChatClient:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        cache: KeyValueCache | None = None,
    ) -> None:
        self._transport = transport
        self._cache: KeyValueCache = cache if cache is not None else _MemoryCache()

    async def _access_token(self, http: httpx.AsyncClient) -> str:
        cached = await self._cache.get(ACCESS_TOKEN_KEY)
        if cached:
            return cached
        settings = get_settings()
        params = {
            "grant_type": "client_credential",
            "appid": settings.WX_APPID,
            "secret": settings.WX_SECRET,
        }
        try:
            resp = await http.get(TOKEN_URL, params=params)
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise WeChatQrError(f"wechat token request failed: {e}") from e
        if data.get("errcode"):
            raise WeChatQrError(f"{data['errcode']}: {data.get('errmsg', '')}")
        token = data.get("access_token")
        if not token:
            raise WeChatQrError("wechat response missing access_token")
        ttl = int(data.get("expires_in", 7200)) - 300
        if ttl > 0:
            await self._cache.set(ACCESS_TOKEN_KEY, token, ttl)
        return token

    async def wxacode(self, scene: str) -> bytes:
        settings = get_settings()
        body = {
            "scene": scene,
            "page": settings.WX_QR_PAGE,
            "env_version": settings.WX_QR_ENV_VERSION,
            "check_path": False,
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=10) as http:
            for attempt in (1, 2):
                token = await self._access_token(http)
                try:
                    resp = await http.post(
                        WXACODE_URL, params={"access_token": token}, json=body
                    )
                except httpx.HTTPError as e:
                    raise WeChatQrError(f"wechat request failed: {e}") from e
                err = _error_json(resp)
                if err is None:
                    return resp.content
                if err.get("errcode") == 40001 and attempt == 1:
                    await self._cache.delete(ACCESS_TOKEN_KEY)
                    continue
                raise WeChatQrError(f"{err.get('errcode')}: {err.get('errmsg', '')}")
        raise WeChatQrError("unreachable")  # pragma: no cover

    async def code2session(self, code: str) -> WxSession:
        settings = get_settings()
        params = {
            "appid": settings.WX_APPID,
            "secret": settings.WX_SECRET,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=10) as http:
            try:
                resp = await http.get(JSCODE2SESSION_URL, params=params)
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                raise WeChatAuthError(f"wechat request failed: {e}") from e
        if data.get("errcode"):
            raise WeChatAuthError(f"{data['errcode']}: {data.get('errmsg', '')}")
        if not data.get("openid"):
            raise WeChatAuthError("wechat response missing openid")
        return WxSession(openid=data["openid"], unionid=data.get("unionid"))


def get_wechat_client() -> WeChatClient:
    from app.weblogin.store import get_ticket_store  # local import: store imports this module

    return HttpWeChatClient(cache=get_ticket_store())