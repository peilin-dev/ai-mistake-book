"""Admin commands, run inside the backend container:

    python -m app.admin_cli reset-password <login_name>

Prints only the temporary password (nothing else on stdout).
"""
import argparse
import asyncio
import secrets
import sys

from sqlalchemy import select

from app.auth.passwords import hash_password
from app.config import get_settings
from app.db import make_engine
from app.models import Teacher

# No look-alike characters (0/O/1/I/l).
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def _temp_password() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(12))


async def reset_password(login_name: str) -> str | None:
    """Set a fresh temporary password; returns it, or None if the login name does not exist."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = make_engine(get_settings().DATABASE_URL)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            teacher = (
                await db.execute(select(Teacher).where(Teacher.login_name == login_name.strip().lower()))
            ).scalar_one_or_none()
            if teacher is None:
                return None
            password = _temp_password()
            teacher.password_hash = hash_password(password)
            await db.commit()
            return password
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    rp = sub.add_parser("reset-password", help="generate a temporary password for a login name")
    rp.add_argument("login_name")
    args = parser.parse_args(argv)
    if args.command == "reset-password":
        password = asyncio.run(reset_password(args.login_name))
        if password is None:
            print("login name not found", file=sys.stderr)
            return 1
        print(password)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
