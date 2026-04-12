import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, hash_password, verify_password
from app.core.exceptions import (
    AccountDisabledError,
    DuplicateEmailError,
    DuplicateUsernameError,
    InvalidCredentialsError,
)
from app.models.user import User
from app.schemas.user import TokenResponse, UserRegister

logger = logging.getLogger(__name__)


async def register_user(db: AsyncSession, data: UserRegister) -> User:
    # Check username
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise DuplicateUsernameError()

    # Check email
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise DuplicateEmailError()

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        display_name=data.display_name or data.username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_user(db: AsyncSession, username: str, password: str) -> TokenResponse:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    # Always run password verification to prevent timing-based user enumeration.
    # When user is not found, verify against a dummy hash so the response time
    # is indistinguishable from an incorrect-password attempt.
    _dummy_hash = "$2b$12$LJ3m4ys3Lz0Y1vVTqHKZaeflVbOBGSJl6Nnb3CiZ3sCImt9Ghmiy"
    if not verify_password(password, user.hashed_password if user else _dummy_hash) or user is None:
        raise InvalidCredentialsError()

    if not user.is_active:
        raise AccountDisabledError()

    token = create_access_token(user.id, user.password_version)
    return TokenResponse(access_token=token)


async def change_user_password(
    db: AsyncSession,
    user: User,
    old_password: str,
    new_password: str,
    client_ip: str | None = None,
) -> TokenResponse:
    """Change the password for an authenticated user.

    Security properties:
    - Old password is verified with constant-time bcrypt comparison.
    - New password strength is validated upstream via Pydantic schema.
    - New password must differ from the old one (prevents accidental no-ops
      and casual forwarding of the old password as the new one).
    - password_version is incremented, which invalidates every previously
      issued JWT for this user via the get_current_user dependency check.
    - OAuth-only users naturally cannot pass the old_password check because
      their hashed_password was seeded from a server-generated random value
      that they never learned; no special-casing needed in the backend.
    - Old/new passwords are never logged.
    """

    if not verify_password(old_password, user.hashed_password):
        logger.warning(
            "change_password_failed user_id=%s reason=wrong_old ip=%s",
            user.id,
            client_ip,
        )
        raise InvalidCredentialsError("当前密码不正确")

    if verify_password(new_password, user.hashed_password):
        raise InvalidCredentialsError("新密码不能与当前密码相同")

    user.hashed_password = hash_password(new_password)
    user.password_version = (user.password_version or 0) + 1
    user.password_changed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "change_password_success user_id=%s new_version=%s ip=%s",
        user.id,
        user.password_version,
        client_ip,
    )

    token = create_access_token(user.id, user.password_version)
    return TokenResponse(access_token=token)
