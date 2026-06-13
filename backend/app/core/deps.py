from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_token
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    token_payload = verify_token(credentials.credentials)
    if token_payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")

    user_id, token_pwd_v = token_payload
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")
    if user.password_version != token_pwd_v:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="凭证已失效，请重新登录")
    return user


async def resolve_optional_user(token: str | None, db: AsyncSession) -> User | None:
    """Resolve a raw bearer token to a user using the given session.

    Pure helper with no FastAPI dependency injection, so callers that must
    NOT hold a request-scoped session for their whole lifetime can resolve
    the user inside their own short-lived session instead. The SSE chat
    stream is the motivating case: a ``Depends(get_optional_user)`` there
    pinned a PG connection for the full 60-120s LLM window (the generator's
    lifetime), so it now reads the token off the request and calls this from
    its prep-phase session. Returns None for missing/invalid/expired tokens
    or disabled users — identical rules to ``get_optional_user``.
    """
    if not token:
        return None
    token_payload = verify_token(token)
    if token_payload is None:
        return None
    user_id, token_pwd_v = token_payload
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if user is None or user.password_version != token_pwd_v:
        return None
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    return await resolve_optional_user(credentials.credentials if credentials else None, db)
