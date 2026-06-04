from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: int | None = None
    master_id: str | None = None
    # Reading context (sent when AI is invoked from the reader page).
    # selected_text / page_content caps must accommodate real CBETA juan
    # lengths — many fascicles (e.g. 大般若經) exceed 50K chars and the
    # whole juan rides along as page_content when a user asks from the
    # reader. The previous 1000 / 15000 caps rejected those requests with
    # a generic 422 before the service-side truncation in
    # ``_build_reader_context_prompt`` (500 / 10000 chars into the LLM
    # context) ever got a chance to run, surfacing as "请求失败，请重试"
    # for every long-juan reader question. Caps are now sized to admit
    # any practical CBETA payload; the LLM-context safety cut still
    # happens server-side regardless of what the client sent.
    text_id: int | None = None
    juan_num: int | None = None
    selected_text: str | None = Field(None, max_length=5000)
    page_content: str | None = Field(None, max_length=200000)
    # Welcome-card shortcut: when set, backend swaps the user turn sent to
    # the LLM for the matching hot-question prompt template, keeping the
    # natural display_text in history/RAG.
    hot_question_id: int | None = None
    # Per-message model override — id from llm_catalog.CATALOG (e.g. "deepseek:v4-pro").
    # Unknown ids fall back gracefully so stale localStorage doesn't break chat.
    model_id: str | None = None
    # File attachments uploaded via POST /chat/attachments. The service
    # prepends each attachment's parsed text to the user message before
    # the LLM call. Ownership is enforced server-side: a logged-in user
    # may only reference their own rows or anonymous (user_id IS NULL)
    # rows; an anonymous request may only reference anonymous rows.
    attachment_ids: list[int] | None = None


class HotQuestionCard(BaseModel):
    id: int
    category: str
    display_text: str


class HotQuestionCardsResponse(BaseModel):
    questions: list[HotQuestionCard]


class FeedbackRequest(BaseModel):
    feedback: Literal["up", "down"] | None = None


class ParallelChunk(BaseModel):
    """A cross-canon parallel passage linked via alignment_pairs.

    Used in trilingual RAG: when the primary RAG hit is a 汉文 chunk that has
    aligned Pali/Tibetan parallels in alignment_pairs, those parallels ride
    along on the ChatSource so the LLM can reference them and the frontend
    citation drawer can show side-by-side tabs.
    """
    text_id: int
    juan_num: int
    chunk_index: int
    chunk_text: str
    lang: str
    title: str = ""
    confidence: float = 1.0


class ChatSource(BaseModel):
    text_id: int
    juan_num: int
    chunk_index: int = 0
    chunk_text: str
    score: float
    title_zh: str = ""
    # Trilingual RAG additions (all optional for backward compat with stored
    # chat history predating this migration).
    lang: str = "lzh"
    source_id: int | None = None
    parallel_chunks: list[ParallelChunk] = []


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


class ShareQARequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    answer: str = Field(..., min_length=1, max_length=20000)
    sources: list[ChatSource] | None = None


class ShareQACreateResponse(BaseModel):
    id: str
    url: str


class ShareQAResponse(BaseModel):
    id: str
    question: str
    answer: str
    sources: list[ChatSource] | None
    view_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
