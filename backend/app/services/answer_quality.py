from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer_review import AnswerReview
from app.models.chat import ChatMessage

# --- Detection config -------------------------------------------------------
# Calibrated 2026-06-30 to ~p10 of the live max(source.score) distribution
# (p10≈0.366), so weak_evidence flags only the bottom decile of retrieval
# strength rather than ~the bottom quartile. ChatSource.score is the blended
# vector+rerank score. Re-read score_distribution from the queue endpoint and
# adjust if the corpus/reranker changes.
WEAK_EVIDENCE_THRESHOLD = 0.37
ABNORMAL_MIN_CHARS = 20

# Prefixes of LLM-failure replies (see chat._FAILED_ANSWER_PREFIXES). Failed /
# empty generations are bugs, not reviewable answers — they are excluded from
# the queue entirely (the chat save-guard stops new ones; this defends against
# legacy junk rows already in the table).
_FAILED_ANSWER_PREFIXES = ("抱歉，AI 服务", "AI 服务返回", "您的 API Key 无效")

# reason tag -> base weight in the suspicion score.
#
# 判据是「引用是否可核对」,不是「有没有引经」。旧的 no_citation(= 无任何来源)
# 把闲聊/元问题("what can you do today?")和真实的引用失败混为一谈,制造了 715
# 条噪音、淹没了信号,已删除。
WEIGHTS = {
    "downvoted": 5.0,
    "fabricated_citation": 4.0,
    "quote_relaxed": 3.0,
    "abnormal": 3.0,
    "citation_corrected": 2.0,
    "weak_evidence": 1.0,  # plus a graded bonus, see classify_answer
}


@dataclass(frozen=True)
class DiagnosticSignals:
    """一条回答在 *入库前* 的引用真相,来自 chat_answer_diagnostics。

    必须从这张表读,不能对 chat_messages.content 重算:verify_quoted_content 的
    契约是「fojin 从不端出假的逐字引用」,对不上原文的引号在保存前就被剥掉了
    (quote_verifier.py:373-382),重算只会得到「一切正常」。"""

    citation_count: int
    source_count: int
    quote_mutation_count: int
    citation_mutation_count: int
    max_source_score: float | None


def _is_failed_answer(content: str | None) -> bool:
    """Empty answer or a known LLM-failure reply — excluded from the queue."""
    text = (content or "").strip()
    return not text or text.startswith(_FAILED_ANSWER_PREFIXES)


def _max_source_score(sources) -> float | None:
    """Max blended score across an assistant message's cited passages, or None
    when there are no parseable sources. Defensive against null/odd JSON."""
    if not sources:
        return None
    try:
        scores = [
            float(s["score"])
            for s in sources
            if isinstance(s, dict) and s.get("score") is not None
        ]
    except (TypeError, ValueError):
        return None
    return max(scores) if scores else None


def _clean_sources(sources) -> list[dict]:
    """Defensive view of an answer's ``sources`` for the response model: always
    a list of dicts that carry a ``text_id`` (the only required schema field).
    A null / non-list / malformed persisted ``sources`` yields ``[]`` so a
    no-citation or odd-JSON item never raises during serialization — the same
    "never raise" contract the detection side already honors."""
    if not isinstance(sources, list):
        return []
    return [
        s for s in sources if isinstance(s, dict) and s.get("text_id") is not None
    ]


def _requested_categories(category: str | None) -> set[str]:
    if not category:
        return set()
    return {c.strip() for c in category.split(",") if c.strip()}


def classify_answer(
    content: str | None, feedback: str | None, diag: DiagnosticSignals
) -> tuple[list[str], float]:
    """Pure detector. 给定一条回答的列 + 它的诊断行,返回命中的标签与可疑度
    (0.0 = 不可疑)。失败/空回答在上游过滤,不在这里打分。"""
    tags: list[str] = []
    score = 0.0

    if feedback == "down":
        tags.append("downvoted")
        score += WEIGHTS["downvoted"]

    if len((content or "").strip()) < ABNORMAL_MIN_CHARS:
        tags.append("abnormal")
        score += WEIGHTS["abnormal"]

    # 引了经却零来源 = 凭空引用,最严重的可核对性失败。
    if diag.citation_count > 0 and diag.source_count == 0:
        tags.append("fabricated_citation")
        score += WEIGHTS["fabricated_citation"]

    # 系统把「转述当原文引」降级过 —— 用户看到的是修好的,但这条本来是错的。
    if diag.quote_mutation_count > 0:
        tags.append("quote_relaxed")
        score += WEIGHTS["quote_relaxed"]

    if diag.citation_mutation_count > 0:
        tags.append("citation_corrected")
        score += WEIGHTS["citation_corrected"]

    mss = diag.max_source_score
    if mss is not None and mss < WEAK_EVIDENCE_THRESHOLD:
        tags.append("weak_evidence")
        # graded: deeper below threshold => more suspect.
        # 注:gap 最大只有 WEAK_EVIDENCE_THRESHOLD(0.37),所以 0.5 这个封顶永远够
        # 不着 —— 生产旧代码自带的死枝,此处保持原样不动:改评分语义会让 SQL 侧的
        # 排序表达式与这里算出的显示分数对不上。
        score += WEIGHTS["weak_evidence"] + min(WEAK_EVIDENCE_THRESHOLD - mss, 0.5) * 2.0

    return tags, round(score, 3)


def _percentiles(samples: list[float]) -> dict[str, float | None]:
    if not samples:
        return {"p10": None, "p25": None, "p50": None, "p90": None}
    s = sorted(samples)

    def pct(p: int) -> float:
        idx = min(int(p / 100 * len(s)), len(s) - 1)
        return round(s[idx], 3)

    return {"p10": pct(10), "p25": pct(25), "p50": pct(50), "p90": pct(90)}


@dataclass
class QueueItem:
    message_id: int
    session_id: int
    answer: str
    sources: list | None
    reason_tags: list[str]
    suspicion_score: float
    feedback: str | None
    created_at: datetime
    question: str = ""


async def _attach_questions(db: AsyncSession, items: list[QueueItem]) -> None:
    """Fill each item's ``question`` with the latest user message strictly
    before that answer in the same session (display only)."""
    if not items:
        return
    session_ids = {it.session_id for it in items}
    rows = (
        await db.execute(
            select(
                ChatMessage.session_id, ChatMessage.content, ChatMessage.created_at
            )
            .where(
                ChatMessage.role == "user",
                ChatMessage.session_id.in_(session_ids),
            )
            .order_by(ChatMessage.created_at)
        )
    ).all()
    by_session: dict[int, list[tuple[datetime, str]]] = {}
    for sid, content, created in rows:
        by_session.setdefault(sid, []).append((created, content))
    for it in items:
        # ``<=`` not ``<``: the user question and its assistant answer are saved
        # in one transaction and share an identical created_at (server-side
        # transaction_timestamp), so a strict ``<`` would drop the very question
        # that produced the answer. The answer itself is role='assistant' and was
        # already excluded by the role=='user' query above, so ``<=`` is safe.
        prior = [
            c for (ts, c) in by_session.get(it.session_id, []) if ts <= it.created_at
        ]
        it.question = prior[-1] if prior else ""


async def build_bad_answer_queue(
    db: AsyncSession,
    *,
    window_days: int = 90,
    min_suspicion: float = 0.0,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Live-compute the ranked queue of suspect assistant answers, excluding
    any message already reviewed."""
    since = datetime.now(UTC) - timedelta(days=window_days)
    requested_categories = _requested_categories(category)
    reviewed = select(AnswerReview.message_id)
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.role == "assistant",
                ChatMessage.created_at >= since,
                ChatMessage.id.not_in(reviewed),
            )
            .order_by(ChatMessage.created_at.desc())
        )
    ).scalars().all()

    items: list[QueueItem] = []
    score_samples: list[float] = []
    for m in rows:
        # Failed/empty generations are bugs, not reviewable answers — never
        # surface them in the quality queue (nor let them skew the score
        # distribution used for calibration).
        if _is_failed_answer(m.content):
            continue
        ms = _max_source_score(m.sources)
        if ms is not None:
            score_samples.append(ms)
        tags, score = classify_answer(m.content, m.sources, m.feedback)
        if not tags or score < min_suspicion:
            continue
        if requested_categories and not requested_categories.intersection(tags):
            continue
        items.append(
            QueueItem(
                message_id=m.id,
                session_id=m.session_id,
                answer=m.content,
                sources=_clean_sources(m.sources),
                reason_tags=tags,
                suspicion_score=score,
                feedback=m.feedback,
                created_at=m.created_at,
            )
        )

    items.sort(key=lambda x: x.suspicion_score, reverse=True)
    total = len(items)
    page = items[offset : offset + limit]
    await _attach_questions(db, page)

    return {
        "total_unreviewed": total,
        "score_distribution": _percentiles(score_samples),
        # Plain dicts (not QueueItem dataclasses) so the AnswerQueueResponse
        # response_model validates cleanly without from_attributes coercion.
        "items": [asdict(it) for it in page],
    }


async def upsert_review(
    db: AsyncSession,
    *,
    message_id: int,
    verdict: str,
    failure_category: str | None,
    note: str | None,
    reviewed_by: int | None,
) -> int:
    """Create/update the review for a message, snapshotting why it was flagged.
    Returns the count of still-unreviewed suspect messages in the last 90 days.
    Raises ValueError if the message does not exist or is not an assistant
    message."""
    msg = (
        await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    ).scalar_one_or_none()
    if msg is None or msg.role != "assistant":
        raise ValueError("message not found or not an assistant message")

    tags, score = classify_answer(msg.content, msg.sources, msg.feedback)
    existing = (
        await db.execute(
            select(AnswerReview).where(AnswerReview.message_id == message_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.verdict = verdict
        existing.failure_category = failure_category
        existing.note = note
        existing.detection_reasons = tags
        existing.suspicion_score = score
        existing.reviewed_by = reviewed_by
        existing.reviewed_at = datetime.now(UTC)
    else:
        db.add(
            AnswerReview(
                message_id=message_id,
                verdict=verdict,
                failure_category=failure_category,
                note=note,
                detection_reasons=tags,
                suspicion_score=score,
                reviewed_by=reviewed_by,
            )
        )
    await db.commit()

    result = await build_bad_answer_queue(db, limit=0)
    return result["total_unreviewed"]


async def review_stats(db: AsyncSession) -> dict:
    rows = (
        await db.execute(
            select(
                AnswerReview.verdict,
                AnswerReview.failure_category,
                AnswerReview.reviewed_at,
            )
        )
    ).all()
    good = sum(1 for v, _c, _t in rows if v == "good")
    bad = sum(1 for v, _c, _t in rows if v == "bad")
    by_category: dict[str, int] = {}
    for _v, c, _t in rows:
        if c:
            by_category[c] = by_category.get(c, 0) + 1
    last = max((t for _v, _c, t in rows if t is not None), default=None)
    return {
        "reviewed_total": len(rows),
        "good": good,
        "bad": bad,
        "by_category": by_category,
        "last_reviewed_at": last,
    }
