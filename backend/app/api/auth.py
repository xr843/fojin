import secrets

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import decrypt_api_key, encrypt_api_key
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    ApiKeyRequest,
    ApiKeyStatus,
    ChangePasswordRequest,
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
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = None
    return await change_user_password(
        db,
        user,
        old_password=data.old_password,
        new_password=data.new_password,
        client_ip=client_ip,
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
    user.encrypted_api_key = encrypt_api_key(data.api_key)
    user.api_provider = data.provider
    user.api_model = data.model
    user.api_custom_url = data.custom_url if data.provider == "custom" else None
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
        key = decrypt_api_key(user.encrypted_api_key)
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
    await db.commit()
    return {"ok": True}


# ── OAuth: GitHub ────────────────────────────────────────────


@router.get("/github/login")
async def github_login(request: Request):
    """Return GitHub OAuth authorization URL as JSON."""
    state = secrets.token_urlsafe(16)
    redis_client = request.app.state.redis
    await redis_client.set(f"oauth_state:{state}", "github", ex=600)
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
    if stored != "github":
        return RedirectResponse(url=f"{settings.oauth_redirect_base}/login?error=invalid_state")
    await redis_client.delete(f"oauth_state:{state}")

    try:
        token_resp = await github_callback(code, db)
        return RedirectResponse(
            url=f"{settings.oauth_redirect_base}/login?token={token_resp.access_token}&provider=github"
        )
    except Exception:
        return RedirectResponse(url=f"{settings.oauth_redirect_base}/login?error=github_failed")


# ── OAuth: Google ────────────────────────────────────────────


@router.get("/google/login")
async def google_login(request: Request):
    """Return Google OAuth authorization URL as JSON."""
    state = secrets.token_urlsafe(16)
    redis_client = request.app.state.redis
    await redis_client.set(f"oauth_state:{state}", "google", ex=600)
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
    if stored != "google":
        return RedirectResponse(url=f"{settings.oauth_redirect_base}/login?error=invalid_state")
    await redis_client.delete(f"oauth_state:{state}")

    try:
        token_resp = await google_callback(code, db)
        return RedirectResponse(
            url=f"{settings.oauth_redirect_base}/login?token={token_resp.access_token}&provider=google"
        )
    except Exception:
        return RedirectResponse(url=f"{settings.oauth_redirect_base}/login?error=google_failed")


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
    redis_client = request.app.state.redis
    valid = await verify_sms_code(data.phone, data.code, redis_client)
    if not valid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    return await sms_login(data.phone, db)
