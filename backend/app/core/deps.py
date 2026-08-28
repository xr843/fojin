from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_token
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

# Key on request.state where a *successfully authenticated* request leaves what
# TokenRenewalMiddleware needs to mint a replacement. Only ever set after the
# password_version check has passed, so renewal can never resurrect a session
# the user revoked by changing their password. `scope["state"]` is shared
# between the dependency's Request and the middleware's (verified, not assumed).
RENEWABLE_STATE_ATTR = "fojin_renewable_token"


def _mark_renewable(request: Request | None, token: str, user: User) -> None:
    if request is None:
        return
    setattr(request.state, RENEWABLE_STATE_ATTR, (token, user.id, user.password_version))


def clear_renewable(request: Request) -> None:
    """Cancel this request's renewal credential.

    For endpoints that revoke the very token they were called with — anything
    that bumps ``password_version``. The auth dependency stamps the credential
    (including the *old* version) before the endpoint body runs, so without
    this the middleware happily mints a replacement at a version that no longer
    exists: a token that is dead the moment it is signed, handed back in
    ``X-Renewed-Token`` for the client to adopt.

    The frontend survives it by overwriting with the token in the response body
    a beat later, but "correct only because something else corrects it" is not
    a property to rely on — and any other client that honours the header would
    simply be logged out.
    """
    if hasattr(request.state, RENEWABLE_STATE_ATTR):
        delattr(request.state, RENEWABLE_STATE_ATTR)


async def get_current_user(
    request: Request,
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
    _mark_renewable(request, credentials.credentials, user)
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
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    token = credentials.credentials if credentials else None
    user = await resolve_optional_user(token, db)
    if user is not None and token:
        _mark_renewable(request, token, user)
    return user
