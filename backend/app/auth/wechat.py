from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings

JSCODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WeChatAuthError(Exception):
    pass


@dataclass(frozen=True)
class WxSession:
    openid: str
    unionid: str | None = None


class WeChatClient(Protocol):
    async def code2session(self, code: str) -> WxSession: ...


class HttpWeChatClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

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
    return HttpWeChatClient()