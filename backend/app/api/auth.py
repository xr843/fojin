import json
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.client_ip import get_real_client_ip
from app.core.crypto import decrypt_api_key, encrypt_api_key
from app.core.deps import get_current_user
from app.core.url_security import normalize_public_https_url
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    ApiKeyRequest,
    ApiKeyStatus,
    ChangePasswordRequest,
    OAuthExchangeRequest,
    TokenResponse,
    UserLogin,
    UserProfile,
    UserRegister,
)
from app.services.auth import change_user_password, login_user, register_user
from app.services.oauth import (
    github_authorize_url,
    github_callback,
    google_authorize_url,
    google_callback,
    send_sms_code,
    sms_login,
    verify_sms_code,
)

logger = logging.getLogger(__name__)

# One-time OAuth exchange code lifetime (seconds). Short by design — the
# frontend should redeem the code immediately after redirect.
OAUTH_EXCHANGE_TTL = 5
OAUTH_EXCHANGE_PREFIX = "oauth:exchange:"

# The OAuth `state` is mirrored into this cookie so the callback can prove the
# flow was started by *this* browser. Redis alone can't: its stored value is
# just the provider name, so any state an attacker minted for themselves
# validates for everyone — login CSRF, where the victim ends up silently
# signed into the attacker's account.
OAUTH_STATE_COOKIE = "fojin_oauth_state"
OAUTH_STATE_TTL = 600


def _set_oauth_state_cookie(response, state: str) -> None:
    """Bind the state to this browser.

    SameSite must be ``lax``: the callback is a cross-site top-level GET
    navigation back from github.com / accounts.google.com, and ``strict``
    would withhold the cookie there and break every login. ``lax`` still
    blocks the cross-site POST/subresource cases that matter here.

    Path is scoped to the auth routes so the cookie isn't attached to every
    request on the origin.
    """
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=OAUTH_STATE_TTL,
        httponly=True,
        samesite="lax",
        secure=settings.oauth_redirect_base.startswith("https://"),
        path="/api/auth",
    )


def _state_is_valid(request: Request, state: str, stored: str | None, provider: str) -> bool:
    """Both the Redis record and this browser's cookie must agree."""
    if stored != provider:
        return False
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE)
    return bool(cookie_state) and secrets.compare_digest(cookie_state, state)


async def _store_oauth_exchange(redis_client, token_resp: TokenResponse, provider: str) -> str:
    """Stash a token in Redis under a one-time code; return the code.

    The code is short-lived (OAUTH_EXCHANGE_TTL) and is consumed atomically
    via GETDEL on the exchange endpoint.
    """
    code = secrets.token_urlsafe(16)
    payload = json.dumps(
        {
            "access_token": token_resp.access_token,
            "token_type": token_resp.token_type,
            "provider": provider,
        }
    )
    await redis_client.set(f"{OAUTH_EXCHANGE_PREFIX}{code}", payload, ex=OAUTH_EXCHANGE_TTL)
    return code


router = APIRouter(prefix="/auth", tags=["auth"])


def _user_to_profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        has_api_key=bool(user.encrypted_api_key),
        api_provider=user.api_provider,
        api_model=user.api_model,
    )


@router.post("/register", response_model=UserProfile)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """注册新用户。"""
    user = await register_user(db, data)
    return _user_to_profile(user)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """用户登录，返回 JWT token。"""
    return await login_user(db, data.username, data.password)


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改当前登录用户的密码。

    成功后返回一张全新的 JWT（原 JWT 因 password_version 递增而失效），
    前端应立刻用返回的新 token 替换本地存储的旧 token。
    同一用户在其他设备上的所有旧 JWT 都会在下一次请求时变成 401。
    """
    client_ip = get_real_client_ip(request, default=None)
    user_agent = request.headers.get("user-agent")
    return await change_user_password(
        db,
        user,
        old_password=data.old_password,
        new_password=data.new_password,
        client_ip=client_ip,
        user_agent=user_agent,
    )


@router.get("/me", response_model=UserProfile)
async def me(user: User = Depends(get_current_user)):
    """获取当前用户信息。"""
    return _user_to_profile(user)


# --- BYOK API Key Management ---


@router.put("/api-key", response_model=ApiKeyStatus)
async def save_api_key(
    data: ApiKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存用户自己的 API Key（加密存储）。"""
    custom_url = None
    if data.provider == "custom":
        try:
            custom_url = normalize_public_https_url(data.custom_url, label="自定义 API 地址")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    cipher, kdf_ver = encrypt_api_key(data.api_key)
    user.encrypted_api_key = cipher
    user.api_key_kdf_version = kdf_ver
    user.api_provider = data.provider
    user.api_model = data.model
    user.api_custom_url = custom_url
    await db.commit()
    key = data.api_key
    return ApiKeyStatus(
        has_api_key=True,
        provider=data.provider,
        model=data.model,
        key_preview=f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "***",
        custom_url=user.api_custom_url,
    )


@router.get("/api-key", response_model=ApiKeyStatus)
async def get_api_key_status(user: User = Depends(get_current_user)):
    """查看 API Key 配置状态（不返回明文）。"""
    if not user.encrypted_api_key:
        return ApiKeyStatus(has_api_key=False)
    try:
        key = decrypt_api_key(user.encrypted_api_key, user.api_key_kdf_version)
        preview = f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "***"
    except Exception:
        preview = None
    return ApiKeyStatus(
        has_api_key=True,
        provider=user.api_provider,
        model=user.api_model,
        key_preview=preview,
        custom_url=user.api_custom_url,
    )


@router.delete("/api-key")
async def delete_api_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除用户的 API Key。"""
    user.encrypted_api_key = None
    user.api_provider = None
    user.api_model = None
    user.api_custom_url = None
    # Free of ciphertext → claim the current KDF so the next save doesn't
    # round-trip through v1.
    from app.core.crypto import KDF_VERSION_V2

    user.api_key_kdf_version = KDF_VERSION_V2
    await db.commit()
    return {"ok": True}


@router.post("/api-key/rotate-encryption")
async def rotate_api_key_encryption(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-encrypt the user's stored BYOK key under the current KDF.

    Escape hatch for the v1→v2 migration: if the bulk migrate script
    can't decrypt a row (because JWT_SECRET_KEY was rotated before this
    fix landed), the row stays at v1 and chat returns "decrypt failed".
    The user can re-save their key from the UI — but if they don't have
    the plaintext anymore, this endpoint at least lets them confirm
    they're already on v2.  Idempotent: a v2 row stays v2.
    """
    if not user.encrypted_api_key:
        raise HTTPException(status_code=404, detail="No API key configured")
    try:
        plaintext = decrypt_api_key(user.encrypted_api_key, user.api_key_kdf_version)
    except Exception as exc:
        logger.warning("Rotate-encryption decrypt failed for user %s: %s", user.id, exc)
        # 409 rather than 500 — this is a "your stored ciphertext is no
        # longer recoverable" state, not a server bug.  Frontend should
        # tell the user to re-enter their key.
        raise HTTPException(
            status_code=409,
            detail="Stored API key cannot be decrypted; please re-enter it.",
        ) from None
    cipher, kdf_ver = encrypt_api_key(plaintext)
    user.encrypted_api_key = cipher
    user.api_key_kdf_version = kdf_ver
    await db.commit()
    return {"ok": True, "kdf_version": kdf_ver}


# ── OAuth: GitHub ────────────────────────────────────────────


@router.get("/github/login")
async def github_login(request: Request, response: Response):
    """Return GitHub OAuth authorization URL as JSON."""
    state = secrets.token_urlsafe(16)
    redis_client = request.app.state.redis
    await redis_client.set(f"oauth_state:{state}", "github", ex=OAUTH_STATE_TTL)
    _set_oauth_state_cookie(response, state)
    return {"url": github_authorize_url(state)}


@router.get("/github/callback")
async def github_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """GitHub OAuth callback — exchange code for JWT, redirect to frontend."""
    redis_client = request.app.state.redis
    stored = await redis_client.get(f"oauth_state:{state}")
    if not _state_is_valid(request, state, stored, "github"):
        return RedirectResponse(url=f"{settings.oauth_redirect_base}/login?error=invalid_state")
    await redis_client.delete(f"oauth_state:{state}")

    try:
        token_resp = await github_callback(code, db)
        exchange_code = await _store_oauth_exchange(redis_client, token_resp, "github")
        redirect = RedirectResponse(url=f"{settings.oauth_redirect_base}/login?provider=github&code={exchange_code}")
    except Exception:
        redirect = RedirectResponse(url=f"{settings.oauth_redirect_base}/login?error=github_failed")
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth")
    return redirect


# ── OAuth: Google ────────────────────────────────────────────


@router.get("/google/login")
async def google_login(request: Request, response: Response):
    """Return Google OAuth authorization URL as JSON."""
    state = secrets.token_urlsafe(16)
    redis_client = request.app.state.redis
    await redis_client.set(f"oauth_state:{state}", "google", ex=OAUTH_STATE_TTL)
    _set_oauth_state_cookie(response, state)
    return {"url": google_authorize_url(state)}


@router.get("/google/callback")
async def google_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Google OAuth callback — exchange code for JWT, redirect to frontend."""
    redis_client = request.app.state.redis
    stored = await redis_client.get(f"oauth_state:{state}")
    if not _state_is_valid(request, state, stored, "google"):
        return RedirectResponse(url=f"{settings.oauth_redirect_base}/login?error=invalid_state")
    await redis_client.delete(f"oauth_state:{state}")

    try:
        token_resp = await google_callback(code, db)
        exchange_code = await _store_oauth_exchange(redis_client, token_resp, "google")
        redirect = RedirectResponse(url=f"{settings.oauth_redirect_base}/login?provider=google&code={exchange_code}")
    except Exception:
        redirect = RedirectResponse(url=f"{settings.oauth_redirect_base}/login?error=google_failed")
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth")
    return redirect


# ── OAuth: one-time code exchange ────────────────────────────


@router.post("/oauth/exchange", response_model=TokenResponse)
async def oauth_exchange(
    data: OAuthExchangeRequest,
    request: Request,
):
    """Exchange a short-lived OAuth code for a JWT.

    The OAuth provider callback redirects the browser to the frontend with
    only an opaque code in the URL. The frontend POSTs that code here to
    obtain the actual JWT — keeping the JWT out of nginx access logs,
    browser history, and Referer headers.

    The code is consumed atomically (GETDEL) and is single-use.
    """
    redis_client = request.app.state.redis
    key = f"{OAUTH_EXCHANGE_PREFIX}{data.code}"

    # Atomic get-and-delete. Falls back to GET+DELETE on older Redis.
    raw = None
    try:
        raw = await redis_client.getdel(key)
    except AttributeError:
        raw = await redis_client.get(key)
        if raw is not None:
            await redis_client.delete(key)

    if not raw:
        raise HTTPException(status_code=401, detail="code expired or invalid")

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="code expired or invalid") from exc

    access_token = payload.get("access_token")
    provider = payload.get("provider")
    if not access_token:
        raise HTTPException(status_code=401, detail="code expired or invalid")

    # Audit log: provider + user_id (decoded from JWT) + client IP. Never
    # log the exchange code itself.
    client_ip = get_real_client_ip(request, default=None)

    user_id = None
    try:
        from app.core.auth import verify_token

        verified = verify_token(access_token)
        if verified is not None:
            user_id = verified[0]
    except Exception:
        # Audit logging must not break the exchange.
        pass

    logger.info(
        "oauth_exchange success provider=%s user_id=%s ip=%s",
        provider,
        user_id,
        client_ip,
    )

    return TokenResponse(
        access_token=access_token,
        token_type=payload.get("token_type", "bearer"),
    )


# ── SMS Login ────────────────────────────────────────────────


class SmsCodeRequest(BaseModel):
    phone: str


class SmsLoginRequest(BaseModel):
    phone: str
    code: str


@router.post("/sms/send-code")
async def send_sms_verification(data: SmsCodeRequest, request: Request):
    """Send SMS verification code to the given phone number."""
    phone = data.phone.strip()
    if not phone or len(phone) < 10:
        return {"ok": False, "message": "请输入有效的手机号码"}

    redis_client = request.app.state.redis
    ok = await send_sms_code(phone, redis_client)
    if not ok:
        return {"ok": False, "message": "发送过于频繁，请稍后再试"}
    return {"ok": True, "message": "验证码已发送"}


@router.post("/sms/login", response_model=TokenResponse)
async def sms_verification_login(
    data: SmsLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Verify SMS code and login (or register if new user)."""
    phone = data.phone.strip()
    redis_client = request.app.state.redis
    valid = await verify_sms_code(phone, data.code, redis_client)
    if not valid:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    return await sms_login(phone, db)
