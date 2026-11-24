from datetime import datetime

from pydantic import BaseModel, Field

from app.services.study_memory import MAX_NOTES_CHARS


class StudyMemoryReading(BaseModel):
    text_id: int
    title_zh: str
    juan_num: int
    last_read_at: datetime


class StudyMemoryTopic(BaseModel):
    session_id: int
    title: str
    last_at: datetime


class StudyMemoryExcerpt(BaseModel):
    text_id: int
    title_zh: str
    juan_num: int
    quote: str


class StudyMemoryResponse(BaseModel):
    """小津记得的内容——与交给模型的是同一份（关掉时三张列表为空）。"""

    enabled: bool
    notes: str | None
    reading: list[StudyMemoryReading]
    topics: list[StudyMemoryTopic]
    excerpts: list[StudyMemoryExcerpt]
    max_notes_chars: int = MAX_NOTES_CHARS
    # 记忆此刻是否进入作答（服务端总开关）。为 false 时前端不说「小津会参考」，也不收偏好。
    used_in_answers: bool = False


class StudyMemoryUpdate(BaseModel):
    enabled: bool
    notes: str | None = Field(default=None, max_length=MAX_NOTES_CHARS)
