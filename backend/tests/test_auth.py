from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from sqlalchemy import select

from app.auth.tokens import decode_token, issue_token
from app.auth.wechat import HttpWeChatClient, WeChatAuthError, WxSession
from app.config import get_settings
from app.models import Teacher


async def login(client, fake_wx, code="c1", openid="o1", unionid="u1"):
    fake_wx.sessions[code] = WxSession(openid=openid, unionid=unionid)
    r = await client.post("/api/auth/wx-login", json={"code": code})
    assert r.status_code == 200
    return r.json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def test_first_login_creates_teacher_without_profile(client, fake_wx):
    fake_wx.sessions["c1"] = WxSession(openid="o1", unionid="u1")
    r = await client.post("/api/auth/wx-login", json={"code": "c1"})
    assert r.status_code == 200
    assert r.json()["teacher"]["display_name"] is None
    assert decode_token(r.json()["token"]) == r.json()["teacher"]["id"]


async def test_same_unionid_returns_same_teacher_and_updates_openid(client, fake_wx, db):
    fake_wx.sessions["c1"] = WxSession(openid="o1", unionid="u1")
    fake_wx.sessions["c2"] = WxSession(openid="o2-new-appid", unionid="u1")
    a = (await client.post("/api/auth/wx-login", json={"code": "c1"})).json()
    b = (await client.post("/api/auth/wx-login", json={"code": "c2"})).json()
    assert a["teacher"]["id"] == b["teacher"]["id"]
    t = (await db.execute(select(Teacher).where(Teacher.id == a["teacher"]["id"]))).scalar_one()
    assert t.mp_openid == "o2-new-appid"


async def test_openid_only_login_then_unionid_backfilled(client, fake_wx, db):
    fake_wx.sessions["c1"] = WxSession(openid="o1", unionid=None)
    fake_wx.sessions["c2"] = WxSession(openid="o1", unionid="u9")
    a = (await client.post("/api/auth/wx-login", json={"code": "c1"})).json()
    b = (await client.post("/api/auth/wx-login", json={"code": "c2"})).json()
    assert a["teacher"]["id"] == b["teacher"]["id"]
    t = (await db.execute(select(Teacher).where(Teacher.id == a["teacher"]["id"]))).scalar_one()
    assert t.unionid == "u9"


async def test_different_users_get_different_teachers(client, fake_wx):
    a = await login(client, fake_wx, "c1", "o1", "u1")
    b = await login(client, fake_wx, "c2", "o2", "u2")
    assert a["teacher"]["id"] != b["teacher"]["id"]


async def test_invalid_code_401(client, fake_wx):
    r = await client.post("/api/auth/wx-login", json={"code": "bad"})
    assert r.status_code == 401


async def test_me_requires_token(client):
    r = await client.get("/api/me")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_me_rejects_garbage_and_expired_token(client, settings):
    r = await client.get("/api/me", headers=bearer("garbage"))
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=5)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    r = await client.get("/api/me", headers=bearer(expired))
    assert r.status_code == 401


async def test_me_rejects_token_for_deleted_teacher(client):
    r = await client.get("/api/me", headers=bearer(issue_token(999999)))
    assert r.status_code == 401


def test_token_roundtrip_and_seven_day_expiry(settings):
    token = issue_token(42)
    assert decode_token(token) == 42
    claims = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    assert claims["sub"] == "42"
    delta = datetime.fromtimestamp(claims["exp"], timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=6, hours=23) < delta <= timedelta(days=7)


async def test_get_me(client, fake_wx):
    data = await login(client, fake_wx)
    r = await client.get("/api/me", headers=bearer(data["token"]))
    assert r.status_code == 200
    assert r.json() == {"id": data["teacher"]["id"], "display_name": None, "last_subject": None,
                        "login_name": None,
                        "quota_total": get_settings().FREE_MONTHLY_PAGES, "quota_used": 0}


async def test_me_includes_quota(auth_client, settings, my_assignment, make_page):
    settings.MONTHLY_PAGE_QUOTA = 7
    await make_page(1)
    await make_page(2)
    body = (await auth_client.get("/api/me")).json()
    assert body["quota_total"] == 7 and body["quota_used"] == 2


async def test_patch_me_display_name(client, fake_wx):
    h = bearer((await login(client, fake_wx))["token"])
    r = await client.patch("/api/me", json={"display_name": "  王老师  "}, headers=h)
    assert r.status_code == 200
    assert r.json()["display_name"] == "王老师"
    assert (await client.get("/api/me", headers=h)).json()["display_name"] == "王老师"
    r = await client.patch("/api/me", json={"display_name": "   "}, headers=h)
    assert r.json()["display_name"] is None
    r = await client.patch("/api/me", json={"display_name": "a" * 32}, headers=h)
    assert r.status_code == 200
    r = await client.patch("/api/me", json={"display_name": "a" * 33}, headers=h)
    assert r.status_code == 422


def _http_client(handler, settings):
    settings.WX_APPID, settings.WX_SECRET = "appid", "secret"
    return HttpWeChatClient(transport=httpx.MockTransport(handler))


async def test_http_client_success(settings):
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        assert request.url.host == "api.weixin.qq.com"
        assert request.url.path == "/sns/jscode2session"
        return httpx.Response(200, json={"openid": "o1", "unionid": "u1", "session_key": "k"})

    s = await _http_client(handler, settings).code2session("abc")
    assert s == WxSession(openid="o1", unionid="u1")
    assert seen == {
        "appid": "appid", "secret": "secret", "js_code": "abc", "grant_type": "authorization_code",
    }


async def test_http_client_no_unionid(settings):
    handler = lambda r: httpx.Response(200, json={"openid": "o1", "session_key": "k"})  # noqa: E731
    s = await _http_client(handler, settings).code2session("abc")
    assert s == WxSession(openid="o1", unionid=None)


async def test_http_client_errcode_raises(settings):
    handler = lambda r: httpx.Response(  # noqa: E731
        200, json={"errcode": 40029, "errmsg": "invalid code"}
    )
    with pytest.raises(WeChatAuthError):
        await _http_client(handler, settings).code2session("abc")