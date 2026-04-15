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
    page_content: str | None = Field(None, max_length=15000)
    # Welcome-card shortcut: when set, backend swaps the user turn sent to
    # the LLM for the matching hot-question prompt template, keeping the
    # natural display_text in history/RAG.
    hot_question_id: int | None = None


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
