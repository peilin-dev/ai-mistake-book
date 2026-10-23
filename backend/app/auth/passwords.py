import base64
import hashlib
import hmac
import secrets

# 16 MiB of memory per hash: fine on a 2-core / 2 GB server.
_N, _R, _P = 2**14, 8, 1
_MAXMEM = 64 * 1024 * 1024
_DKLEN = 32


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=_DKLEN
    )


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(pw, salt, _N, _R, _P)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(pw: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = _scrypt(pw, salt, int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# A real hash of a random password, used to spend the same time when a login name is unknown.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def dummy_verify(pw: str) -> None:
    verify_password(pw, _DUMMY_HASH)
