from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import issue_token
from app.auth.wechat import WeChatAuthError, WeChatClient, get_wechat_client
from app.config import get_settings
from app.deps import current_teacher, get_db
from app.models import Subject, Teacher
from app.quota.service import pages_used_this_month

router = APIRouter()


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


async def _me_out(db: AsyncSession, teacher: Teacher) -> MeOut:
    return MeOut(
        id=teacher.id,
        display_name=teacher.display_name,
        last_subject=teacher.last_subject,
        quota_total=get_settings().MONTHLY_PAGE_QUOTA,
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
        teacher = Teacher(unionid=sess.unionid, mp_openid=sess.openid)
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
            teacher = Teacher(unionid=None, mp_openid="dev-login")
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