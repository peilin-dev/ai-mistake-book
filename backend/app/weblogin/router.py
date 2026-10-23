import base64
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import TeacherBrief
from app.auth.tokens import issue_token
from app.auth.wechat import WeChatClient, WeChatQrError, get_wechat_client
from app.deps import current_teacher, get_db
from app.models import Teacher
from app.weblogin.store import TicketStore, get_ticket_store

router = APIRouter()

TICKET_TTL_S = 300
RATE_LIMIT = 10
RATE_WINDOW_S = 60
EXPIRED_DETAIL = "二维码已过期，请在电脑上刷新"


def _key(ticket: str) -> str:
    return f"weblogin:{ticket}"


class TicketOut(BaseModel):
    ticket: str
    poll_key: str
    pair_code: str
    qr_png: str
    expires_in: int


class PollOut(BaseModel):
    status: str
    expires_in: int = 0
    token: str | None = None
    teacher: TeacherBrief | None = None


class ScanOut(BaseModel):
    pair_code: str


def _client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


@router.post("/web-login/tickets", response_model=TicketOut, status_code=201)
async def create_ticket(
    request: Request,
    store: TicketStore = Depends(get_ticket_store),
    wx: WeChatClient = Depends(get_wechat_client),
):
    count = await store.incr(f"weblogin:rate:{_client_ip(request)}", RATE_WINDOW_S)
    if count > RATE_LIMIT:
        raise HTTPException(status_code=429, detail="操作太频繁，请稍后再试")
    ticket = secrets.token_urlsafe(12)
    try:
        png = await wx.wxacode(ticket)
    except WeChatQrError:
        raise HTTPException(status_code=503, detail="二维码生成失败，请稍后再试") from None
    poll_key = secrets.token_urlsafe(24)
    pair_code = f"{secrets.randbelow(10000):04d}"
    await store.set_json(
        _key(ticket),
        {"poll_key": poll_key, "pair_code": pair_code, "status": "pending", "teacher_id": None},
        TICKET_TTL_S,
    )
    return TicketOut(
        ticket=ticket,
        poll_key=poll_key,
        pair_code=pair_code,
        qr_png=base64.b64encode(png).decode(),
        expires_in=TICKET_TTL_S,
    )


@router.get("/web-login/tickets/{ticket}", response_model=PollOut)
async def poll_ticket(
    ticket: str,
    poll_key: str,
    store: TicketStore = Depends(get_ticket_store),
    db: AsyncSession = Depends(get_db),
):
    data = await store.get_json(_key(ticket))
    if data is None:
        return PollOut(status="expired")
    if not secrets.compare_digest(data["poll_key"], poll_key):
        raise HTTPException(status_code=404, detail="not found")
    expires_in = await store.ttl(_key(ticket))
    if data["status"] == "confirmed":
        teacher = await db.get(Teacher, data["teacher_id"])
        await store.delete(_key(ticket))
        if teacher is None:
            return PollOut(status="expired")
        return PollOut(
            status="confirmed",
            expires_in=expires_in,
            token=issue_token(teacher.id),
            teacher=TeacherBrief(id=teacher.id, display_name=teacher.display_name),
        )
    return PollOut(status=data["status"], expires_in=expires_in)


async def _load(store: TicketStore, ticket: str) -> dict:
    data = await store.get_json(_key(ticket))
    if data is None:
        raise HTTPException(status_code=410, detail=EXPIRED_DETAIL)
    return data


async def _save(store: TicketStore, ticket: str, data: dict) -> None:
    ttl = await store.ttl(_key(ticket))
    if ttl <= 0:
        raise HTTPException(status_code=410, detail=EXPIRED_DETAIL)
    await store.set_json(_key(ticket), data, ttl)


@router.post("/web-login/tickets/{ticket}:scan", response_model=ScanOut)
async def scan_ticket(
    ticket: str,
    teacher: Teacher = Depends(current_teacher),
    store: TicketStore = Depends(get_ticket_store),
):
    data = await _load(store, ticket)
    if data["status"] == "pending":
        data["status"] = "scanned"
        data["teacher_id"] = teacher.id
        await _save(store, ticket, data)
    elif data["teacher_id"] != teacher.id or data["status"] != "scanned":
        raise HTTPException(status_code=409, detail="二维码已被使用")
    return ScanOut(pair_code=data["pair_code"])


async def _decide(ticket: str, teacher: Teacher, store: TicketStore, new_status: str) -> Response:
    data = await _load(store, ticket)
    if data["status"] != "scanned" or data["teacher_id"] != teacher.id:
        raise HTTPException(status_code=409, detail="二维码状态不对，请在电脑上刷新")
    data["status"] = new_status
    await _save(store, ticket, data)
    return Response(status_code=204)


@router.post("/web-login/tickets/{ticket}:confirm", status_code=204)
async def confirm_ticket(
    ticket: str,
    teacher: Teacher = Depends(current_teacher),
    store: TicketStore = Depends(get_ticket_store),
):
    return await _decide(ticket, teacher, store, "confirmed")


@router.post("/web-login/tickets/{ticket}:cancel", status_code=204)
async def cancel_ticket(
    ticket: str,
    teacher: Teacher = Depends(current_teacher),
    store: TicketStore = Depends(get_ticket_store),
):
    return await _decide(ticket, teacher, store, "cancelled")
