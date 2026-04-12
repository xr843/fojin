import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    display_name: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码长度至少8位")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("密码必须包含字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含数字")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("新密码长度至少8位")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("新密码必须包含字母")
        if not re.search(r"\d", v):
            raise ValueError("新密码必须包含数字")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    display_name: str | None = None
    role: str = "user"
    is_active: bool
    created_at: datetime
    has_api_key: bool = False
    api_provider: str | None = None
    api_model: str | None = None

    model_config = {"from_attributes": True}


class ApiKeyRequest(BaseModel):
    api_key: str
    provider: str = "openai"
    model: str | None = None
    custom_url: str | None = None  # Only used when provider="custom"


class ApiKeyStatus(BaseModel):
    has_api_key: bool
    provider: str | None = None
    model: str | None = None
    key_preview: str | None = None  # e.g. "sk-...3xF2"
    custom_url: str | None = None
