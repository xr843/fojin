from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: int | None = None
    master_id: str | None = None
    # Reading context (sent when AI is invoked from the reader page)
    text_id: int | None = None
    juan_num: int | None = None
    selected_text: str | None = Field(None, max_length=1000)


class FeedbackRequest(BaseModel):
    feedback: Literal["up", "down"] | None = None


class ChatSource(BaseModel):
    text_id: int
    juan_num: int
    chunk_text: str
    score: float
    title_zh: str = ""


class ChatResponse(BaseModel):
    session_id: int
    message: str
    sources: list[ChatSource]


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: list[ChatSource] | None
    feedback: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionResponse(BaseModel):
    id: int
    title: str | None
    messages: list[ChatMessageResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionListItem(BaseModel):
    id: int
    title: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
