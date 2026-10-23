import base64

import httpx

from app.auth.tokens import decode_token
from app.main import create_app

BASE = "/api/web-login/tickets"


async def _create(client) -> dict:
    r = await client.post(BASE)
    assert r.status_code == 201, r.text
    return r.json()


def _decode(token: str) -> dict:
    return {"sub": decode_token(token)}


async def test_create_ticket_returns_qr_and_pair_code(client, fake_wx, fake_tickets):
    body = await _create(client)
    assert fake_wx.scenes == [body["ticket"]]
    assert len(body["ticket"]) == 16
    assert len(body["pair_code"]) == 4 and body["pair_code"].isdigit()
    assert body["expires_in"] == 300
    assert base64.b64decode(body["qr_png"]) == b"\x89PNG-fake"
    assert body["poll_key"] not in body["ticket"]


async def test_create_ticket_wechat_error_503(client, app, fake_tickets):
    from app.auth.wechat import WeChatQrError, get_wechat_client

    class Boom:
        async def wxacode(self, scene):
            raise WeChatQrError("x")

    app.dependency_overrides[get_wechat_client] = lambda: Boom()
    r = await client.post(BASE)
    assert r.status_code == 503
    assert r.json()["detail"] == "二维码生成失败，请稍后再试"


async def test_create_ticket_rate_limited(client, fake_tickets):
    for _ in range(10):
        await _create(client)
    r = await client.post(BASE)
    assert r.status_code == 429
    assert r.json()["detail"] == "操作太频繁，请稍后再试"


async def test_poll_requires_poll_key(client, fake_tickets):
    t = await _create(client)
    assert (await client.get(f"{BASE}/{t['ticket']}")).status_code in (404, 422)
    assert (await client.get(f"{BASE}/{t['ticket']}?poll_key=wrong")).status_code == 404
    r = await client.get(f"{BASE}/{t['ticket']}?poll_key={t['poll_key']}")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    assert r.json()["token"] is None


async def test_poll_unknown_ticket_is_expired(client, fake_tickets):
    r = await client.get(f"{BASE}/nope?poll_key=x")
    assert r.status_code == 200
    assert r.json()["status"] == "expired"


async def test_scan_confirm_then_poll_gets_token(client, client_for, teacher, fake_tickets):
    t = await _create(client)
    poll = f"{BASE}/{t['ticket']}?poll_key={t['poll_key']}"
    phone = client_for(teacher)

    r = await phone.post(f"{BASE}/{t['ticket']}:scan")
    assert r.status_code == 200
    assert r.json() == {"pair_code": t["pair_code"]}
    assert (await client.get(poll)).json()["status"] == "scanned"

    assert (await phone.post(f"{BASE}/{t['ticket']}:confirm")).status_code == 204
    r = await client.get(poll)
    body = r.json()
    assert body["status"] == "confirmed"
    assert int(_decode(body["token"])["sub"]) == teacher.id
    assert body["teacher"]["id"] == teacher.id


async def test_scan_requires_login(client, fake_tickets):
    t = await _create(client)
    assert (await client.post(f"{BASE}/{t['ticket']}:scan")).status_code == 401


async def test_token_handed_out_once(client, client_for, teacher, fake_tickets):
    t = await _create(client)
    poll = f"{BASE}/{t['ticket']}?poll_key={t['poll_key']}"
    phone = client_for(teacher)
    await phone.post(f"{BASE}/{t['ticket']}:scan")
    await phone.post(f"{BASE}/{t['ticket']}:confirm")
    assert (await client.get(poll)).json()["token"]
    again = (await client.get(poll)).json()
    assert again["status"] == "expired" and again["token"] is None


async def test_confirm_only_by_the_teacher_who_scanned(
    client, client_for, teacher, make_teacher, fake_tickets
):
    other = await make_teacher()
    t = await _create(client)
    mine, theirs = client_for(teacher), client_for(other)
    # confirm before scan
    assert (await mine.post(f"{BASE}/{t['ticket']}:confirm")).status_code == 409
    assert (await mine.post(f"{BASE}/{t['ticket']}:scan")).status_code == 200
    assert (await theirs.post(f"{BASE}/{t['ticket']}:scan")).status_code == 409
    assert (await theirs.post(f"{BASE}/{t['ticket']}:confirm")).status_code == 409
    assert (await theirs.post(f"{BASE}/{t['ticket']}:cancel")).status_code == 409
    assert (await mine.post(f"{BASE}/{t['ticket']}:confirm")).status_code == 204


async def test_cancel_then_poll_is_cancelled(client, client_for, teacher, fake_tickets):
    t = await _create(client)
    phone = client_for(teacher)
    await phone.post(f"{BASE}/{t['ticket']}:scan")
    assert (await phone.post(f"{BASE}/{t['ticket']}:cancel")).status_code == 204
    r = await client.get(f"{BASE}/{t['ticket']}?poll_key={t['poll_key']}")
    assert r.json()["status"] == "cancelled"
    assert r.json()["token"] is None


async def test_state_change_keeps_ttl(client, client_for, teacher, fake_tickets):
    t = await _create(client)
    fake_tickets.data[f"weblogin:{t['ticket']}"] = (
        fake_tickets.data[f"weblogin:{t['ticket']}"][0],
        120,
    )
    await client_for(teacher).post(f"{BASE}/{t['ticket']}:scan")
    assert await fake_tickets.ttl(f"weblogin:{t['ticket']}") == 120


async def test_expired_ticket_scan_is_410(client, client_for, teacher, fake_tickets):
    t = await _create(client)
    fake_tickets.expire(f"weblogin:{t['ticket']}")
    phone = client_for(teacher)
    for action in ("scan", "confirm", "cancel"):
        r = await phone.post(f"{BASE}/{t['ticket']}:{action}")
        assert r.status_code == 410
        assert r.json()["detail"] == "二维码已过期，请在电脑上刷新"


async def test_dev_login_creates_teacher_when_none(settings, db):
    settings.DEV_LOGIN = True
    app = create_app()
    from app.deps import get_db

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.post("/api/auth/dev-login", json={})
    assert r.status_code == 200
    assert decode_token(r.json()["token"]) == r.json()["teacher"]["id"]


async def test_dev_login_absent_unless_enabled(client, teacher, settings, db, fake_wx):
    r = await client.post("/api/auth/dev-login", json={})
    assert r.status_code in (404, 405)

    settings.DEV_LOGIN = True
    app = create_app()
    from app.deps import get_db

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.post("/api/auth/dev-login", json={})
        assert r.status_code == 200
        assert r.json()["teacher"]["id"] == teacher.id
        assert int(_decode(r.json()["token"])["sub"]) == teacher.id
        r = await c.post("/api/auth/dev-login", json={"teacher_id": teacher.id})
        assert r.status_code == 200
        r = await c.post("/api/auth/dev-login", json={"teacher_id": 999999})
        assert r.status_code == 404
