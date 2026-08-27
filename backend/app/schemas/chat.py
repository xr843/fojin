from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    # message cap raised from 2000 → 20000 to admit the natural reader
    # workflow where a user pastes a multi-paragraph passage into the
    # input as their "question" (e.g. "解读以下这段经文：…"). 2000 chars
    # ≈ 660 Chinese characters and was routinely overshot, surfacing as
    # a generic 422 → "请求失败，请重试" on the frontend. 20000 chars
    # comfortably fits any single-message LLM payload (≈ 6-7K tokens for
    # CJK) and still keeps a hard upper guard against DoS / runaway
    # paste accidents. Frontend has no client-side maxLength on this
    # input so the backend cap is the only wall; pick it generously.
    message: str = Field(..., min_length=1, max_length=20000)
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
    # 「重新生成」：同一问题再答一次，替换本会话最后一轮问答 —— 拼上下文时去掉
    # 那一轮（否则模型多半照抄上一个答案），新答案成功落库时删旧的那对。
    # 只对最后一轮生效；不做从中间分叉。
    regenerate: bool = False
    # Per-message model override — id from llm_catalog.CATALOG (e.g. "deepseek:v4-pro").
    # Unknown ids fall back gracefully so stale localStorage doesn't break chat.
    model_id: str | None = None
    # File attachments uploaded via POST /chat/attachments. The service
    # prepends each attachment's parsed text to the user message before
    # the LLM call. Ownership is enforced server-side: a logged-in user
    # may only reference their own rows or anonymous (user_id IS NULL)
    # rows; an anonymous request may only reference anonymous rows.
    #
    # The cap matters for more than ergonomics: anonymous rows are readable
    # by any anonymous caller, and the single-use `consumed_at` guard only
    # holds if an attacker has to probe sequential ids one at a time. An
    # uncapped list let one request sweep every unconsumed upload — and bill
    # the platform LLM key for all of their parsed text at once.
    attachment_ids: list[int] | None = Field(None, max_length=5)


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
    # Portable cross-canon citation id (fojin:sc/mn10.1 …), None when the
    # source has no cbeta_id or one that wouldn't round-trip. Optional for
    # backward compat with chat history stored before this field existed.
    urn: str | None = None


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
    # Portable cross-canon citation id (fojin:cbeta/T0001.1 …) built from the
    # source's cbeta_id; None when unavailable. Backward-compatible optional.
    urn: str | None = None


ChatTrustState = Literal[
    "verified",
    "citation_corrected",
    # A non-verbatim quote was downgraded to prose (deterministic fix) — a
    # correction tier, not a warning.
    "quote_relaxed",
    # Legacy: emitted by the old caveat-only path; retained so diagnostics
    # persisted before the downgrade change still deserialize.
    "quote_unverified",
    "sources_available",
    "no_sources",
]


class ChatTrustStatus(BaseModel):
    state: ChatTrustState
    citation_count: int = 0
    source_count: int = 0
    citation_mutation_count: int = 0
    quote_mutation_count: int = 0
    # How many 「…」 quotes were actually verbatim-checked against a source.
    # Lets the UI distinguish "cited AND a quote checked out" from "cited but
    # quoted nothing verbatim" — a green "verified" badge alone conflates them.
    # None for historical answers reconstructed from a diagnostic row (the
    # count predates persistence and is not stored).
    quote_checked_count: int | None = None
    max_source_score: float | None = None
    min_source_score: float | None = None


class ChatResponse(BaseModel):
    session_id: int
    message: str
    sources: list[ChatSource]
    trust_status: ChatTrustStatus | None = None


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: list[ChatSource] | None
    trust_status: ChatTrustStatus | None = None
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
    pinned: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionUpdateRequest(BaseModel):
    """Rename and/or (un)pin a session. Omitted fields are left untouched."""

    # 500 is the column width; a sidebar row shows ~20 chars, so anything past
    # 200 is already unreadable there and only serves to bloat the list payload.
    title: str | None = Field(None, min_length=1, max_length=200)
    pinned: bool | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("会话名称不能为空")
        return cleaned


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
