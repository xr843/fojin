from datetime import datetime

from pydantic import BaseModel, Field


class AdminOverview(BaseModel):
    total_users: int
    new_users_today: int
    total_sessions: int
    new_sessions_today: int
    total_messages: int
    new_messages_today: int
    pending_suggestions: int
    pending_annotations: int


class DailyCount(BaseModel):
    date: str
    count: int


class AdminTrends(BaseModel):
    registrations: list[DailyCount]
    messages: list[DailyCount]
    active_users: list[DailyCount]


class AdminUserItem(BaseModel):
    id: int
    username: str
    display_name: str | None
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None

    model_config = {"from_attributes": True}


class AdminUserUpdate(BaseModel):
    role: str | None = Field(None, pattern="^(user|reviewer|admin)$")
    is_active: bool | None = None


class AdminUserListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[AdminUserItem]


class AdminAnnotationItem(BaseModel):
    id: int
    text_id: int
    juan_num: int
    annotation_type: str
    content: str
    user_id: int
    username: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAnnotationListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[AdminAnnotationItem]
