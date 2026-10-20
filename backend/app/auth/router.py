from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import issue_token
from app.auth.wechat import WeChatAuthError, WeChatClient, get_wechat_client
from app.deps import current_teacher, get_db
from app.models import Subject, Teacher

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


@router.get("/me", response_model=MeOut)
async def get_me(teacher: Teacher = Depends(current_teacher)):
    return teacher


@router.patch("/me", response_model=MeOut)
async def patch_me(
    body: MePatch,
    teacher: Teacher = Depends(current_teacher),
    db: AsyncSession = Depends(get_db),
):
    teacher.display_name = body.display_name
    await db.commit()
    return teacher