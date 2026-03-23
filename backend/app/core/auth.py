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


def create_access_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> int | None:
    """Verify JWT token and return user_id, or None if invalid."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return int(user_id)
    except (PyJWTError, ValueError):
        return None
