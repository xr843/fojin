from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_api_key, encrypt_api_key
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import ApiKeyRequest, ApiKeyStatus, TokenResponse, UserLogin, UserProfile, UserRegister
from app.services.auth import login_user, register_user

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
    await db.commit()
    key = data.api_key
    return ApiKeyStatus(
        has_api_key=True,
        provider=data.provider,
        model=data.model,
        key_preview=f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "***",
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
    await db.commit()
    return {"ok": True}
