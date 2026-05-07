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
from app.models.user import PasswordChangeAudit, User
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

    now = datetime.now(UTC)
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        display_name=data.display_name or data.username,
        last_active_at=now,
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

    user.last_active_at = datetime.now(UTC)
    await db.commit()

    token = create_access_token(user.id, user.password_version)
    return TokenResponse(access_token=token)


async def change_user_password(
    db: AsyncSession,
    user: User,
    old_password: str,
    new_password: str,
    client_ip: str | None = None,
    user_agent: str | None = None,
    via: str = "self",
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
    - Every attempt — success and failure — is recorded in the
      ``password_change_audit`` table so a post-incident investigation
      can reconstruct who changed the password from where, even after
      nginx/journalctl logs have rotated. See migration 0127.
    """

    if not verify_password(old_password, user.hashed_password):
        logger.warning(
            "change_password_failed user_id=%s reason=wrong_old ip=%s",
            user.id,
            client_ip,
        )
        await _record_password_audit(db, user.id, "wrong_old_password", via, client_ip, user_agent)
        raise InvalidCredentialsError("当前密码不正确")

    if verify_password(new_password, user.hashed_password):
        await _record_password_audit(db, user.id, "same_as_old", via, client_ip, user_agent)
        raise InvalidCredentialsError("新密码不能与当前密码相同")

    user.hashed_password = hash_password(new_password)
    user.password_version = (user.password_version or 0) + 1
    user.password_changed_at = datetime.now(UTC)
    await _record_password_audit(db, user.id, "success", via, client_ip, user_agent, commit=False)
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


async def _record_password_audit(
    db: AsyncSession,
    user_id: int,
    outcome: str,
    via: str,
    client_ip: str | None,
    user_agent: str | None,
    *,
    commit: bool = True,
) -> None:
    """Append one row to ``password_change_audit``.

    On the success path we batch the audit row into the same transaction
    that flips the user's hashed_password / password_version, so the
    audit either commits with the change or rolls back with it. On the
    failure paths we commit immediately (the user object isn't dirty).

    user_agent is truncated to 500 chars to match the column width;
    long, mostly-noise UAs from headless scanners shouldn't blow up
    inserts.
    """
    db.add(
        PasswordChangeAudit(
            user_id=user_id,
            outcome=outcome,
            via=via,
            ip=client_ip,
            user_agent=(user_agent[:500] if user_agent else None),
        )
    )
    if commit:
        await db.commit()
