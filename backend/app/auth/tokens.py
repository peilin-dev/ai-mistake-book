from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def issue_token(teacher_id: int) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(days=s.JWT_EXPIRE_DAYS)
    return jwt.encode({"sub": str(teacher_id), "exp": exp}, s.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    """Return the teacher id; raise jwt.PyJWTError on any invalid/expired token."""
    claims = jwt.decode(
        token, get_settings().JWT_SECRET, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]}
    )
    try:
        return int(claims["sub"])
    except ValueError as e:
        raise jwt.InvalidTokenError("bad sub") from e