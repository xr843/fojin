from datetime import datetime

from pydantic import BaseModel, Field

# 阅读页划词浮层只对 1–500 字的选区出现，摘录原文上限与之一致。
QUOTE_MAX = 500
NOTE_MAX = 2000


class ExcerptCreate(BaseModel):
    text_id: int
    juan_num: int = Field(ge=1)
    line_ref: str | None = Field(default=None, max_length=16)
    end_line_ref: str | None = Field(default=None, max_length=16)
    quote: str = Field(min_length=1, max_length=QUOTE_MAX)
    note: str | None = Field(default=None, max_length=NOTE_MAX)


class ExcerptUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=NOTE_MAX)


class ExcerptResponse(BaseModel):
    id: int
    text_id: int
    title_zh: str
    cbeta_id: str
    juan_num: int
    line_ref: str | None = None
    end_line_ref: str | None = None
    quote: str
    note: str | None = None
    created_at: datetime


class ExcerptListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[ExcerptResponse]
