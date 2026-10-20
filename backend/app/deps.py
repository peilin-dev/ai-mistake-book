from collections.abc import AsyncIterator

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import decode_token
from app.db import get_sessionmaker
from app.models import Teacher

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def current_teacher(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Teacher:
    unauthorized = HTTPException(
        status_code=401, detail="not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None:
        raise unauthorized
    try:
        teacher_id = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise unauthorized from None
    teacher = await db.get(Teacher, teacher_id)
    if teacher is None:
        raise unauthorized
    return teacher