from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import TokenResponse, UserLogin, UserProfile, UserRegister
from app.services.auth import login_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserProfile)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """注册新用户。"""
    user = await register_user(db, data)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """用户登录，返回 JWT token。"""
    return await login_user(db, data.username, data.password)


@router.get("/me", response_model=UserProfile)
async def me(user: User = Depends(get_current_user)):
    """获取当前用户信息。"""
    return user
