from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AdminOverview(BaseModel):
    total_users: int
    new_users_today: int
    new_users_yesterday: int
    total_sessions: int
    new_sessions_today: int
    new_sessions_yesterday: int
    total_messages: int
    new_messages_today: int
    new_messages_yesterday: int
    pending_suggestions: int
    pending_annotations: int
    last_updated: datetime


class DailyCount(BaseModel):
    date: str
    count: int


class AdminTrends(BaseModel):
    registrations: list[DailyCount]
    messages: list[DailyCount]
    active_users: list[DailyCount]


class ActiveUserDetail(BaseModel):
    """One logged-in user who was active (chatted or read) on a given local day."""

    user_id: int
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    role: str
    chat_messages: int  # role='user' messages that day
    texts_read: int  # ReadingHistory rows touched that day
    last_active_at: datetime | None = None
    api_provider: str | None = None  # BYOK provider, null = uses platform key


class ActiveUserDayDetail(BaseModel):
    date: str
    total: int
    users: list[ActiveUserDetail]


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


class AdminAuditLogItem(BaseModel):
    id: int
    actor_id: int | None
    actor_username: str | None
    action: str
    target_type: str
    target_id: int | None
    detail: dict | None
    created_at: datetime


class AdminAuditLogListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[AdminAuditLogItem]


# --- Module Usage (Umami analytics) ---

class ModuleEventItem(BaseModel):
    event_name: str
    label: str
    count: int


class KeywordItem(BaseModel):
    keyword: str
    count: int


class AnswerQuality(BaseModel):
    """Behavioural answer-quality proxies, sourced from Umami events.

    Rates are percentages against ``chat_questions`` (questions asked); they are
    ``None`` when there is no chat volume in the window.
    """
    chat_questions: int
    citation_click: int
    chat_copy: int
    chat_retry: int
    citation_click_rate: float | None = None
    copy_rate: float | None = None
    retry_rate: float | None = None


class AdminModuleUsage(BaseModel):
    days: int
    events: list[ModuleEventItem]
    top_search_keywords: list[KeywordItem]
    answer_quality: AnswerQuality


# --- Answer-quality bad-answer queue ---

class AnswerQueueSource(BaseModel):
    text_id: int
    juan_num: int = 0
    chunk_index: int = 0
    chunk_text: str = ""
    score: float | None = None
    title_zh: str = ""
    lang: str = ""


class AnswerQueueItem(BaseModel):
    message_id: int
    session_id: int
    question: str
    answer: str
    sources: list[AnswerQueueSource] = Field(default_factory=list)
    reason_tags: list[str]
    suspicion_score: float
    feedback: str | None = None
    created_at: datetime


class ScoreDistribution(BaseModel):
    p10: float | None = None
    p25: float | None = None
    p50: float | None = None
    p90: float | None = None


class AnswerQueueResponse(BaseModel):
    total_unreviewed: int
    score_distribution: ScoreDistribution
    items: list[AnswerQueueItem]


class AnswerReviewCreate(BaseModel):
    message_id: int
    verdict: str = Field(pattern="^(good|bad)$")
    failure_category: str | None = Field(
        None, pattern="^(recall|hallucination|prompt|data|other)$"
    )
    note: str | None = None

    @model_validator(mode="after")
    def validate_failure_category(self) -> "AnswerReviewCreate":
        if self.verdict == "bad" and not self.failure_category:
            raise ValueError("failure_category is required when verdict is bad")
        if self.verdict == "good" and self.failure_category is not None:
            raise ValueError("failure_category must be omitted when verdict is good")
        return self


class AnswerReviewResult(BaseModel):
    ok: bool
    remaining_unreviewed: int


class AnswerReviewStats(BaseModel):
    reviewed_total: int
    good: int
    bad: int
    by_category: dict[str, int]
    last_reviewed_at: datetime | None = None
