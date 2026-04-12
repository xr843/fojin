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


def create_access_token(user_id: int, password_version: int = 0) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "pwd_v": password_version, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


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
