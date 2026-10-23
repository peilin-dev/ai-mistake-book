import asyncio
import hmac
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import captcha as captcha_mod
from app.auth.passwords import dummy_verify, hash_password, verify_password
from app.auth.tokens import issue_token
from app.auth.wechat import WeChatAuthError, WeChatClient, get_wechat_client
from app.config import get_settings
from app.deps import current_teacher, get_db
from app.models import Subject, Teacher
from app.quota.service import pages_used_this_month, quota_limit
from app.weblogin.store import TicketStore, get_ticket_store

router = APIRouter()

CAPTCHA_TTL_S = 300
LOGIN_NAME_RE = re.compile(r"^[a-z0-9_]{4,32}$")
TOO_FREQUENT = "操作太频繁，请稍后再试"
NAME_TAKEN = "这个登录名已经有人用了"
BAD_LOGIN = "登录名或密码不对"
LOCKED = "输错次数太多，请 15 分钟后再试"
BAD_CAPTCHA = "验证码不对或已过期"
BAD_CURRENT = "当前密码不对"
REGISTER_LIMIT, REGISTER_WINDOW_S = 5, 3600
LOGIN_IP_LIMIT, LOGIN_IP_WINDOW_S = 20, 60
CAPTCHA_IP_LIMIT, CAPTCHA_IP_WINDOW_S = 30, 60
MAX_LOGIN_FAILURES, LOCK_S = 5, 900


def _client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _new_teacher(**kw) -> Teacher:
    return Teacher(page_quota=get_settings().FREE_MONTHLY_PAGES, **kw)


class WxLoginIn(BaseModel):
    code: str


class TeacherBrief(BaseModel):
    id: int
    display_name: str | None


class WxLoginOut(BaseModel):
    token: str
    teacher: TeacherBrief


class MeOut(BaseModel):
    id: int
    display_name: str | None
    last_subject: Subject | None
    quota_total: int
    quota_used: int
    login_name: str | None = None


async def _me_out(db: AsyncSession, teacher: Teacher) -> MeOut:
    return MeOut(
        id=teacher.id,
        display_name=teacher.display_name,
        last_subject=teacher.last_subject,
        login_name=teacher.login_name,
        quota_total=quota_limit(teacher),
        quota_used=await pages_used_this_month(db, teacher.id),
    )


class MePatch(BaseModel):
    display_name: str

    @field_validator("display_name")
    @classmethod
    def _clean(cls, v: str) -> str | None:
        v = v.strip()
        if len(v) > 32:
            raise ValueError("display_name must be at most 32 characters")
        return v or None


@router.post("/auth/wx-login", response_model=WxLoginOut)
async def wx_login(
    body: WxLoginIn,
    db: AsyncSession = Depends(get_db),
    wx: WeChatClient = Depends(get_wechat_client),
):
    try:
        sess = await wx.code2session(body.code)
    except WeChatAuthError:
        raise HTTPException(status_code=401, detail="invalid wechat code") from None

    teacher = None
    if sess.unionid:
        teacher = (
            await db.execute(select(Teacher).where(Teacher.unionid == sess.unionid))
        ).scalar_one_or_none()
    if teacher is None:
        teacher = (
            await db.execute(select(Teacher).where(Teacher.mp_openid == sess.openid))
        ).scalar_one_or_none()
    if teacher is None:
        teacher = _new_teacher(unionid=sess.unionid, mp_openid=sess.openid)
        db.add(teacher)
    else:
        if sess.unionid and teacher.unionid is None:
            teacher.unionid = sess.unionid
        if teacher.mp_openid != sess.openid:
            teacher.mp_openid = sess.openid
    await db.commit()
    return WxLoginOut(
        token=issue_token(teacher.id),
        teacher=TeacherBrief(id=teacher.id, display_name=teacher.display_name),
    )


class DevLoginIn(BaseModel):
    teacher_id: int | None = None


# Only included by create_app() when settings.DEV_LOGIN is true.
dev_router = APIRouter()


@dev_router.post("/auth/dev-login", response_model=WxLoginOut)
async def dev_login(body: DevLoginIn, db: AsyncSession = Depends(get_db)):
    if body.teacher_id is not None:
        teacher = await db.get(Teacher, body.teacher_id)
        if teacher is None:
            raise HTTPException(status_code=404, detail="teacher not found")
    else:
        teacher = (
            await db.execute(select(Teacher).order_by(Teacher.id).limit(1))
        ).scalar_one_or_none()
        if teacher is None:
            teacher = _new_teacher(unionid=None, mp_openid="dev-login")
            db.add(teacher)
            await db.commit()
    return WxLoginOut(
        token=issue_token(teacher.id),
        teacher=TeacherBrief(id=teacher.id, display_name=teacher.display_name),
    )


@router.get("/me", response_model=MeOut)
async def get_me(teacher: Teacher = Depends(current_teacher), db: AsyncSession = Depends(get_db)):
    return await _me_out(db, teacher)


@router.patch("/me", response_model=MeOut)
async def patch_me(
    body: MePatch,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    teacher.display_name = body.display_name
    await db.commit()
    return await _me_out(db, teacher)

# --- password registration / login ---


class CaptchaOut(BaseModel):
    captcha_id: str
    image: str


class RegisterIn(BaseModel):
    login_name: str = Field(max_length=200)
    password: str = Field(max_length=200)
    captcha_id: str = Field(max_length=100)
    captcha_code: str = Field(max_length=20)


class LoginIn(BaseModel):
    login_name: str = Field(max_length=200)
    password: str = Field(max_length=200)


class CredentialsIn(BaseModel):
    login_name: str = Field(max_length=200)
    password: str = Field(max_length=200)
    current_password: str | None = Field(default=None, max_length=200)


def _clean_name(raw: str) -> str:
    name = raw.strip().lower()
    if not LOGIN_NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="登录名需要 4-32 位，只能用字母、数字和下划线")
    return name


def _check_password(pw: str) -> None:
    if not 8 <= len(pw) <= 64:
        raise HTTPException(status_code=400, detail="密码需要 8-64 位")


def _brief(teacher: Teacher) -> WxLoginOut:
    return WxLoginOut(
        token=issue_token(teacher.id),
        teacher=TeacherBrief(id=teacher.id, display_name=teacher.display_name),
    )


@router.post("/auth/captcha", response_model=CaptchaOut)
async def create_captcha(request: Request, store: TicketStore = Depends(get_ticket_store)):
    if await store.incr(f"captcha:ip:{_client_ip(request)}", CAPTCHA_IP_WINDOW_S) > CAPTCHA_IP_LIMIT:
        raise HTTPException(status_code=429, detail=TOO_FREQUENT)
    code = captcha_mod.new_code()
    captcha_id = secrets.token_urlsafe(12)
    await store.set_json(f"captcha:{captcha_id}", {"code": code}, CAPTCHA_TTL_S)
    image = await asyncio.to_thread(captcha_mod.render_base64, code)
    return CaptchaOut(captcha_id=captcha_id, image=image)


async def _take_captcha(store: TicketStore, captcha_id: str, code: str) -> bool:
    # Taken (deleted) before comparing: every captcha is good for exactly one attempt.
    data = await store.take_json(f"captcha:{captcha_id}")
    return bool(data) and hmac.compare_digest(
        str(data["code"]).encode(), code.strip().upper().encode()
    )


@router.post("/auth/register", response_model=WxLoginOut, status_code=201)
async def register(
    body: RegisterIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    store: TicketStore = Depends(get_ticket_store),
):
    if await store.incr(f"register:ip:{_client_ip(request)}", REGISTER_WINDOW_S) > REGISTER_LIMIT:
        raise HTTPException(status_code=429, detail=TOO_FREQUENT)
    name = _clean_name(body.login_name)
    _check_password(body.password)
    if not await _take_captcha(store, body.captcha_id, body.captcha_code):
        raise HTTPException(status_code=400, detail=BAD_CAPTCHA)
    taken = (await db.execute(select(Teacher.id).where(Teacher.login_name == name))).first()
    if taken:
        raise HTTPException(status_code=409, detail=NAME_TAKEN)
    teacher = _new_teacher(
        login_name=name, password_hash=await asyncio.to_thread(hash_password, body.password)
    )
    db.add(teacher)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=NAME_TAKEN) from None
    return _brief(teacher)


@router.post("/auth/login", response_model=WxLoginOut)
async def password_login(
    body: LoginIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    store: TicketStore = Depends(get_ticket_store),
):
    if await store.incr(f"login:ip:{_client_ip(request)}", LOGIN_IP_WINDOW_S) > LOGIN_IP_LIMIT:
        raise HTTPException(status_code=429, detail=TOO_FREQUENT)
    name = body.login_name.strip().lower()[:64]
    lock_key, fail_key = f"login:lock:{name}", f"login:fail:{name}"
    if await store.get(lock_key):
        raise HTTPException(status_code=429, detail=LOCKED)
    teacher = (
        await db.execute(select(Teacher).where(Teacher.login_name == name))
    ).scalar_one_or_none()
    if teacher is not None and teacher.password_hash:
        ok = await asyncio.to_thread(verify_password, body.password, teacher.password_hash)
    else:
        await asyncio.to_thread(dummy_verify, body.password)
        ok = False
    if not ok:
        if await store.incr(fail_key, LOCK_S) >= MAX_LOGIN_FAILURES:
            await store.set(lock_key, "1", LOCK_S)
        raise HTTPException(status_code=401, detail=BAD_LOGIN)
    await store.delete(fail_key)
    return _brief(teacher)


@router.put("/me/credentials", response_model=MeOut)
async def set_credentials(
    body: CredentialsIn,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
    store: TicketStore = Depends(get_ticket_store),
):
    name = _clean_name(body.login_name)
    _check_password(body.password)
    if teacher.password_hash:
        fail_key = f"credentials:fail:{teacher.id}"
        if await store.get(f"credentials:lock:{teacher.id}"):
            raise HTTPException(status_code=429, detail=LOCKED)
        current = body.current_password
        if not current or not await asyncio.to_thread(verify_password, current, teacher.password_hash):
            if await store.incr(fail_key, LOCK_S) >= MAX_LOGIN_FAILURES:
                await store.set(f"credentials:lock:{teacher.id}", "1", LOCK_S)
            raise HTTPException(status_code=403, detail=BAD_CURRENT)
        await store.delete(fail_key)
    other = (
        await db.execute(select(Teacher.id).where(Teacher.login_name == name, Teacher.id != teacher.id))
    ).first()
    if other:
        raise HTTPException(status_code=409, detail=NAME_TAKEN)
    teacher.login_name = name
    teacher.password_hash = await asyncio.to_thread(hash_password, body.password)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=NAME_TAKEN) from None
    return await _me_out(db, teacher)