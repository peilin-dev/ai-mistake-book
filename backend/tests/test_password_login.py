import asyncio
import base64

import pytest
from sqlalchemy import select

from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import decode_token
from app.auth.wechat import WxSession
from app.models import Teacher

PW = "correct-horse-1"


async def _captcha(client, store) -> tuple[str, str]:
    r = await client.post("/api/auth/captcha")
    assert r.status_code == 200, r.text
    body = r.json()
    assert base64.b64decode(body["image"])[:4] == b"\x89PNG"
    code = (await store.get_json(f"captcha:{body['captcha_id']}"))["code"]
    return body["captcha_id"], code


async def _register(client, store, name="Teacher_01", password=PW, ip=None, code=None):
    cid, real = await _captcha(client, store)
    headers = {"X-Real-IP": ip} if ip else {}
    return await client.post(
        "/api/auth/register",
        json={"login_name": name, "password": password, "captcha_id": cid,
              "captcha_code": code or real},
        headers=headers,
    )


async def test_hash_and_verify_roundtrip_and_salted():
    h1, h2 = hash_password("abcdefgh1"), hash_password("abcdefgh1")
    assert h1 != h2
    assert h1.startswith("scrypt$16384$8$1$")
    assert len(h1.split("$")) == 6
    assert verify_password("abcdefgh1", h1) and verify_password("abcdefgh1", h2)
    assert not verify_password("abcdefgh2", h1)
    assert not verify_password("x", "garbage")
    assert "abcdefgh1" not in h1


async def test_captcha_single_use_and_case_insensitive(client, fake_tickets):
    r = await client.post("/api/auth/captcha")
    cid = r.json()["captcha_id"]
    code = (await fake_tickets.get_json(f"captcha:{cid}"))["code"]
    assert len(code) == 4 and not set(code) & set("0O1IL")
    assert fake_tickets.data[f"captcha:{cid}"][1] == 300

    body = {"login_name": "abcd", "password": PW, "captcha_id": cid, "captcha_code": code.lower()}
    assert (await client.post("/api/auth/register", json=body)).status_code == 201
    # second use of the same captcha fails even with the right code
    body["login_name"] = "abcde"
    r = await client.post("/api/auth/register", json=body)
    assert r.status_code == 400 and r.json()["detail"] == "验证码不对或已过期"


async def test_register_creates_teacher_with_free_quota_and_logs_in(client, db, fake_tickets, settings):
    r = await _register(client, fake_tickets, name="Teacher_01")
    assert r.status_code == 201, r.text
    body = r.json()
    t = (await db.execute(select(Teacher).where(Teacher.login_name == "teacher_01"))).scalar_one()
    assert decode_token(body["token"]) == t.id
    assert body["teacher"]["id"] == t.id
    assert t.page_quota == settings.FREE_MONTHLY_PAGES == 30
    assert t.password_hash and PW not in t.password_hash
    me = await client.get("/api/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.json()["login_name"] == "teacher_01" and me.json()["quota_total"] == 30


@pytest.mark.parametrize(
    "name,password,detail",
    [
        ("abc", PW, None),
        ("has space", PW, None),
        ("中文名字啊啊", PW, None),
        ("a" * 33, PW, None),
        ("goodname", "short", None),
        ("goodname", "x" * 65, None),
    ],
)
async def test_register_rejects_bad_name_password(client, fake_tickets, name, password, detail):
    r = await _register(client, fake_tickets, name=name, password=password)
    assert r.status_code in (400, 422), r.text


async def test_register_rejects_bad_captcha_and_duplicates(client, db, fake_tickets):
    r = await _register(client, fake_tickets, code="ZZZZ")
    if r.status_code == 201:
        pytest.skip("improbable captcha collision")
    assert r.status_code == 400 and r.json()["detail"] == "验证码不对或已过期"
    # unknown captcha id
    r = await client.post("/api/auth/register", json={
        "login_name": "goodname", "password": PW, "captcha_id": "nope", "captcha_code": "ABCD"})
    assert r.status_code == 400
    assert (await _register(client, fake_tickets, name="dupname")).status_code == 201
    r = await _register(client, fake_tickets, name="DupName")
    assert r.status_code == 409 and r.json()["detail"] == "这个登录名已经有人用了"
    # a wrong guess burns the captcha
    cid, real = await _captcha(client, fake_tickets)
    await client.post("/api/auth/register", json={
        "login_name": "other1", "password": PW, "captcha_id": cid, "captcha_code": "ZZZZ"},
        headers={"X-Real-IP": "6.6.6.6"})
    r = await client.post("/api/auth/register", json={
        "login_name": "other1", "password": PW, "captcha_id": cid, "captcha_code": real},
        headers={"X-Real-IP": "6.6.6.6"})
    assert r.status_code == 400


async def test_register_rate_limited_per_ip(client, fake_tickets):
    for i in range(5):
        r = await _register(client, fake_tickets, name=f"user_{i}1", ip="9.9.9.9")
        assert r.status_code == 201
    r = await _register(client, fake_tickets, name="user_x1", ip="9.9.9.9")
    assert r.status_code == 429 and r.json()["detail"] == "操作太频繁，请稍后再试"
    assert (await _register(client, fake_tickets, name="user_y1", ip="8.8.8.8")).status_code == 201


async def test_failed_register_attempts_do_not_use_up_the_ip_limit(client, fake_tickets):
    ip = "5.5.5.5"
    assert (await _register(client, fake_tickets, name="first_one", ip=ip)).status_code == 201
    for _ in range(6):  # wrong captcha
        r = await _register(client, fake_tickets, name="never_made", ip=ip, code="ZZZZ")
        assert r.status_code in (400, 201)
        if r.status_code == 201:
            pytest.skip("improbable captcha collision")
    for _ in range(6):  # duplicate name
        assert (await _register(client, fake_tickets, name="first_one", ip=ip)).status_code == 409
    for i in range(4):  # 4 more accounts still allowed: 5 in total
        assert (await _register(client, fake_tickets, name=f"later_{i}x", ip=ip)).status_code == 201
    assert (await _register(client, fake_tickets, name="one_more", ip=ip)).status_code == 429


async def _login(client, name, password, ip=None):
    return await client.post("/api/auth/login", json={"login_name": name, "password": password},
                             headers={"X-Real-IP": ip} if ip else {})


async def test_login_success_and_generic_failure_message(client, fake_tickets):
    await _register(client, fake_tickets, name="alice_w")
    r = await _login(client, "ALICE_W", PW)
    assert r.status_code == 200 and "token" in r.json()
    wrong = await _login(client, "alice_w", "wrong-password")
    missing = await _login(client, "nobody_here", "wrong-password")
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"] == "登录名或密码不对"


async def test_login_locks_after_5_failures_then_resets_on_success(client, fake_tickets):
    await _register(client, fake_tickets, name="bobby_1")
    for _ in range(4):
        assert (await _login(client, "bobby_1", "bad-password")).status_code == 401
    # success clears the counter
    assert (await _login(client, "bobby_1", PW)).status_code == 200
    for _ in range(5):
        assert (await _login(client, "bobby_1", "bad-password")).status_code == 401
    r = await _login(client, "bobby_1", PW)
    assert r.status_code == 429 and r.json()["detail"] == "输错次数太多，请 15 分钟后再试"
    # unknown names lock too (no existence leak)
    for _ in range(5):
        await _login(client, "ghost_name", "bad-password")
    r = await _login(client, "ghost_name", "bad-password")
    assert r.status_code == 429
    # lock expires
    fake_tickets.expire("login:lock:bobby_1")
    assert (await _login(client, "bobby_1", PW)).status_code == 200


async def test_login_rate_limited_per_ip(client, fake_tickets):
    for _ in range(20):
        await _login(client, "someone1", "x", ip="7.7.7.7")
    r = await _login(client, "someone1", "x", ip="7.7.7.7")
    assert r.status_code == 429 and r.json()["detail"] == "操作太频繁，请稍后再试"


async def test_set_credentials_first_time_then_change_requires_current_password(
    client_for, teacher, client, fake_tickets, db
):
    c = client_for(teacher)
    r = await c.put("/api/me/credentials", json={"login_name": "Newname1", "password": PW,
                                                  "current_password": None})
    assert r.status_code == 200, r.text
    assert r.json()["login_name"] == "newname1" and r.json()["id"] == teacher.id
    assert (await _login(client, "newname1", PW)).status_code == 200

    r = await c.put("/api/me/credentials", json={"login_name": "newname1", "password": "another-pass1",
                                                  "current_password": None})
    assert r.status_code == 403 and r.json()["detail"] == "当前密码不对"
    r = await c.put("/api/me/credentials", json={"login_name": "newname1", "password": "another-pass1",
                                                  "current_password": "wrong-one-111"})
    assert r.status_code == 403
    r = await c.put("/api/me/credentials", json={"login_name": "newname2", "password": "another-pass1",
                                                  "current_password": PW})
    assert r.status_code == 200 and r.json()["login_name"] == "newname2"
    assert (await _login(client, "newname2", "another-pass1")).status_code == 200
    assert (await _login(client, "newname2", PW)).status_code == 401


async def test_set_credentials_conflict_and_validation(client_for, make_teacher, client, fake_tickets):
    await _register(client, fake_tickets, name="taken_name")
    t = await make_teacher()
    c = client_for(t)
    r = await c.put("/api/me/credentials", json={"login_name": "TAKEN_NAME", "password": PW,
                                                  "current_password": None})
    assert r.status_code == 409 and r.json()["detail"] == "这个登录名已经有人用了"
    r = await c.put("/api/me/credentials", json={"login_name": "ab", "password": PW,
                                                  "current_password": None})
    assert r.status_code in (400, 422)
    r = await client.put("/api/me/credentials", json={"login_name": "abcdef", "password": PW,
                                                       "current_password": None})
    assert r.status_code == 401


async def test_change_password_wrong_current_is_throttled(client_for, teacher, fake_tickets):
    c = client_for(teacher)
    await c.put("/api/me/credentials", json={"login_name": "throttle1", "password": PW,
                                              "current_password": None})
    for _ in range(5):
        r = await c.put("/api/me/credentials", json={"login_name": "throttle1", "password": "zzzzzzzz1",
                                                      "current_password": "bad-bad-bad"})
        assert r.status_code == 403
    r = await c.put("/api/me/credentials", json={"login_name": "throttle1", "password": "zzzzzzzz1",
                                                  "current_password": PW})
    assert r.status_code == 429


async def test_wechat_and_password_reach_the_same_account(client, fake_wx, fake_tickets, db):
    fake_wx.sessions["c1"] = WxSession(openid="wx-open-1", unionid="wx-union-1")
    r = await client.post("/api/auth/wx-login", json={"code": "c1"})
    token, tid = r.json()["token"], r.json()["teacher"]["id"]
    h = {"Authorization": f"Bearer {token}"}
    r = await client.put("/api/me/credentials", headers=h, json={
        "login_name": "wxuser1", "password": PW, "current_password": None})
    assert r.status_code == 200
    r = await _login(client, "wxuser1", PW)
    assert r.json()["teacher"]["id"] == tid
    r = await client.post("/api/auth/wx-login", json={"code": "c1"})
    assert r.json()["teacher"]["id"] == tid


async def test_existing_teachers_keep_300_new_teachers_get_30(client, fake_wx, db, make_teacher, client_for):
    old = await make_teacher()  # page_quota NULL -> falls back to MONTHLY_PAGE_QUOTA (300)
    me = await client_for(old).get("/api/me")
    assert me.json()["quota_total"] == 300
    fake_wx.sessions["n1"] = WxSession(openid="new-open", unionid=None)
    r = await client.post("/api/auth/wx-login", json={"code": "n1"})
    t = await db.get(Teacher, r.json()["teacher"]["id"])
    assert t.page_quota == 30
    dev = await db.execute(select(Teacher).where(Teacher.id == t.id))
    assert dev.scalar_one().page_quota == 30


async def test_quota_enforced_per_teacher(db, make_teacher, settings):
    from app.quota.service import QuotaExceeded, check_quota

    t = await make_teacher()
    t.page_quota = 0
    await db.commit()
    with pytest.raises(QuotaExceeded):
        await check_quota(db, t.id)
    t.page_quota = 5
    await db.commit()
    await check_quota(db, t.id)


async def test_admin_cli_reset_password(client, fake_tickets, db, capsys, monkeypatch):
    from app import admin_cli

    monkeypatch.setattr(admin_cli, "get_ticket_store", lambda: fake_tickets)
    await _register(client, fake_tickets, name="forgot_1")
    assert (await _login(client, "forgot_1", PW)).status_code == 200
    for _ in range(5):
        await _login(client, "forgot_1", "bad-password")
    assert (await _login(client, "forgot_1", PW)).status_code == 429
    # lockout is cleared by an admin reset too is not required; just the password changes
    rc = await asyncio.to_thread(admin_cli.main, ["reset-password", "Forgot_1"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert len(out) == 12 and out.isalnum()
    await db.rollback()  # drop the shared session's stale snapshot
    db.expire_all()
    assert (await _login(client, "forgot_1", PW)).status_code == 401
    assert (await _login(client, "forgot_1", out)).status_code == 200

    rc = await asyncio.to_thread(admin_cli.main, ["reset-password", "no_such_user"])
    assert rc == 1
