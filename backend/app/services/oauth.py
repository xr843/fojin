"""OAuth (GitHub, Google) and SMS login service.

Handles third-party user creation/linking and token issuance.
"""

import json
import logging
import secrets
import string

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import create_access_token, hash_password
from app.models.user import SocialAccount, User
from app.schemas.user import TokenResponse

logger = logging.getLogger(__name__)


async def _find_or_create_user(
    db: AsyncSession,
    provider: str,
    provider_user_id: str,
    email: str | None,
    display_name: str | None,
    provider_data: dict | None = None,
) -> User:
    """Find an existing user linked to this social account, or create a new one."""
    # Check if social account already linked
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.provider == provider,
            SocialAccount.provider_user_id == provider_user_id,
        )
    )
    social = result.scalar_one_or_none()

    if social:
        # Existing link — fetch the user
        user_result = await db.execute(select(User).where(User.id == social.user_id))
        user = user_result.scalar_one()
        return user

    # If we have an email, check if a user with that email already exists
    user = None
    if email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if user is None:
        # Create a new user with a random password
        random_pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))
        # Generate a unique username from provider info
        base_username = f"{provider}_{provider_user_id[:20]}"
        username = base_username
        # Ensure uniqueness
        for _i in range(10):
            result = await db.execute(select(User).where(User.username == username))
            if result.scalar_one_or_none() is None:
                break
            username = f"{base_username}_{secrets.token_hex(3)}"

        user = User(
            username=username,
            email=email or f"{provider}_{provider_user_id}@noreply.fojin.app",
            hashed_password=hash_password(random_pw),
            display_name=display_name or username,
        )
        db.add(user)
        await db.flush()  # Get user.id

    # Link social account
    social = SocialAccount(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        provider_data=json.dumps(provider_data, ensure_ascii=False) if provider_data else None,
    )
    db.add(social)
    await db.commit()
    await db.refresh(user)
    return user


# ── GitHub OAuth ─────────────────────────────────────────────

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


def github_authorize_url(state: str) -> str:
    redirect_uri = f"{settings.oauth_redirect_base}/api/auth/github/callback"
    return (
        f"{GITHUB_AUTH_URL}?client_id={settings.github_client_id}"
        f"&redirect_uri={redirect_uri}&scope=user:email&state={state}"
    )


async def github_callback(code: str, db: AsyncSession) -> TokenResponse:
    """Exchange GitHub code for user token."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Exchange code for access token
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data["access_token"]

        # Fetch user info
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        user_resp = await client.get(GITHUB_USER_URL, headers=headers)
        user_resp.raise_for_status()
        gh_user = user_resp.json()

        # Fetch primary email
        email = gh_user.get("email")
        if not email:
            emails_resp = await client.get(GITHUB_EMAILS_URL, headers=headers)
            if emails_resp.status_code == 200:
                for e in emails_resp.json():
                    if e.get("primary") and e.get("verified"):
                        email = e["email"]
                        break

    user = await _find_or_create_user(
        db,
        provider="github",
        provider_user_id=str(gh_user["id"]),
        email=email,
        display_name=gh_user.get("name") or gh_user.get("login"),
        provider_data={"login": gh_user.get("login"), "avatar_url": gh_user.get("avatar_url")},
    )
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


# ── Google OAuth ─────────────────────────────────────────────

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def google_authorize_url(state: str) -> str:
    redirect_uri = f"{settings.oauth_redirect_base}/api/auth/google/callback"
    return (
        f"{GOOGLE_AUTH_URL}?client_id={settings.google_client_id}"
        f"&redirect_uri={redirect_uri}&response_type=code"
        f"&scope=openid+email+profile&state={state}&access_type=offline"
    )


async def google_callback(code: str, db: AsyncSession) -> TokenResponse:
    """Exchange Google code for user token."""
    redirect_uri = f"{settings.oauth_redirect_base}/api/auth/google/callback"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data["access_token"]

        user_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        g_user = user_resp.json()

    user = await _find_or_create_user(
        db,
        provider="google",
        provider_user_id=g_user["sub"],
        email=g_user.get("email"),
        display_name=g_user.get("name"),
        provider_data={"picture": g_user.get("picture")},
    )
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


# ── SMS Login ────────────────────────────────────────────────


async def send_sms_code(phone: str, redis_client) -> bool:
    """Send a 6-digit verification code via Alibaba Cloud SMS."""
    code = "".join(secrets.choice(string.digits) for _ in range(6))

    # Store in Redis with 5-minute TTL
    key = f"sms_code:{phone}"
    await redis_client.set(key, code, ex=300)

    # Rate limit: 1 SMS per minute
    rate_key = f"sms_rate:{phone}"
    if await redis_client.exists(rate_key):
        return False
    await redis_client.set(rate_key, "1", ex=60)

    if not settings.aliyun_sms_access_key_id:
        # Development mode: log the code instead of sending
        logger.warning("SMS dev mode: phone=%s code=%s", phone, code)
        return True

    # Call Alibaba Cloud SMS API
    try:
        from app.services.aliyun_sms import send_sms
        await send_sms(phone, code)
        return True
    except Exception:
        logger.exception("Failed to send SMS to %s", phone)
        return False


async def verify_sms_code(phone: str, code: str, redis_client) -> bool:
    """Verify the SMS code."""
    key = f"sms_code:{phone}"
    stored = await redis_client.get(key)
    if stored and stored == code:
        await redis_client.delete(key)
        return True
    return False


async def sms_login(phone: str, db: AsyncSession) -> TokenResponse:
    """Login or register via phone number."""
    user = await _find_or_create_user(
        db,
        provider="phone",
        provider_user_id=phone,
        email=None,
        display_name=f"用户{phone[-4:]}",
    )
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)
