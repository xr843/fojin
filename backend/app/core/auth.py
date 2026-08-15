from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from jwt.exceptions import PyJWTError

from app.config import settings


def _truncate(password: str) -> bytes:
    """bcrypt 最多支持 72 字节，超出需截断。"""
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_truncate(password), bcrypt.gensalt()).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(_truncate(plain_password), hashed_password.encode("ascii"))


def create_access_token(
    user_id: int,
    password_version: int = 0,
    *,
    original_issued_at: datetime | None = None,
) -> str:
    """Mint an access token.

    ``original_issued_at`` carries the *session's* start across sliding renewals
    (see app/services/token_renewal.py): a renewed token gets a fresh ``exp`` but
    keeps the original ``oit``, so a chain of renewals still ages against the
    absolute cap instead of living forever. Omit it for a real sign-in — the
    session starts now.
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "pwd_v": password_version,
        "exp": expire,
        "oit": int((original_issued_at or now).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token_claims(token: str) -> dict | None:
    """Full verified payload, or None if the token does not verify.

    ``verify_token`` deliberately narrows to (user_id, password_version) — the
    only things an authorization decision may rest on. Renewal additionally
    needs ``exp`` and ``oit``, hence this second entry point rather than a wider
    return type that every caller would have to ignore.
    """
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except (PyJWTError, ValueError):
        return None


def verify_token(token: str) -> tuple[int, int] | None:
    """Verify JWT token and return (user_id, password_version), or None if invalid.

    Tokens issued before the password_version field was added will have
    pwd_v absent; treat them as version -1 so they never match a user's
    current password_version (>= 0) and force a re-login after deploy.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        pwd_v = payload.get("pwd_v", -1)
        return int(user_id), int(pwd_v)
    except (PyJWTError, ValueError):
        return None
