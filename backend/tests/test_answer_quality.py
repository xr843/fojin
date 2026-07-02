"""Answer-quality queue — pure classifier unit tests + API tests."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.answer_review import AnswerReview
from app.models.chat import ChatMessage, ChatSession
from app.schemas.admin import AnswerReviewCreate
from app.services.answer_quality import (
    WEAK_EVIDENCE_THRESHOLD,
    _is_failed_answer,
    _max_source_score,
    _percentiles,
    build_bad_answer_queue,
    classify_answer,
    upsert_review,
)


def _sources(*scores):
    return [{"text_id": 1, "juan_num": 1, "chunk_text": "x", "score": s} for s in scores]


def test_strong_answer_is_not_suspect():
    tags, score = classify_answer(
        "这是一段足够长且引用了可靠经文的回答，详细解释了五蕴的含义、出处"
        "与彼此关系，并逐一给出对应的经证与上下文脉络，便于读者核对。",
        _sources(0.82, 0.61),
        None,
    )
    assert tags == []
    assert score == 0.0


def test_downvoted_is_flagged():
    tags, score = classify_answer("一段足够长的正常回答" * 3, _sources(0.9), "down")
    assert "downvoted" in tags
    assert score > 0


def test_short_answer_is_flagged_as_abnormal():
    tags, score = classify_answer("不知道", _sources(0.9), None)
    assert tags == ["abnormal"]
    assert score > 0


def test_no_citation_is_flagged():
    tags, _ = classify_answer("一段足够长的正常回答内容" * 3, None, None)
    assert "no_citation" in tags


def test_weak_evidence_is_flagged_and_graded():
    near, score_near = classify_answer(
        "正常长度的回答内容" * 3, _sources(WEAK_EVIDENCE_THRESHOLD - 0.05), None
    )
    far, score_far = classify_answer("正常长度的回答内容" * 3, _sources(0.01), None)
    assert "weak_evidence" in near and "weak_evidence" in far
    assert score_far > score_near  # deeper below threshold => more suspect


def test_multiple_detectors_stack():
    tags, score = classify_answer("短答", None, "down")
    assert {"downvoted", "abnormal", "no_citation"} <= set(tags)
    assert score > 7  # downvoted(5) + abnormal + no_citation(2)


def test_answer_review_create_requires_bad_failure_category():
    with pytest.raises(ValidationError):
        AnswerReviewCreate(message_id=1, verdict="bad")


def test_answer_review_create_rejects_good_failure_category():
    with pytest.raises(ValidationError):
        AnswerReviewCreate(message_id=1, verdict="good", failure_category="recall")


def test_is_failed_answer():
    assert _is_failed_answer("")
    assert _is_failed_answer("   ")
    assert _is_failed_answer(None)
    assert _is_failed_answer("抱歉，AI 服务暂时不可用，请稍后重试。")
    assert _is_failed_answer("AI 服务返回 429：触发限流，请稍后重试。")
    assert not _is_failed_answer("一段正常的佛学回答内容，解释五蕴。")


def test_max_source_score_handles_bad_json():
    assert _max_source_score(None) is None
    assert _max_source_score([]) is None
    assert _max_source_score([{"no_score": 1}]) is None
    assert _max_source_score(_sources(0.3, 0.7)) == 0.7


def test_percentiles_empty_returns_nulls():
    assert _percentiles([]) == {"p10": None, "p25": None, "p50": None, "p90": None}


def test_percentiles_basic():
    p = _percentiles([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    assert p["p10"] <= p["p50"] <= p["p90"]


# --- API auth tests ---


@pytest.mark.anyio
async def test_queue_requires_admin(client):
    resp = await client.get("/api/admin/answer-quality/queue")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_queue_non_admin_forbidden(client):
    from app.core.deps import get_current_user
    from app.main import app

    fake = MagicMock()
    fake.id = 2
    fake.role = "user"
    fake.is_active = True
    app.dependency_overrides[get_current_user] = lambda: fake
    try:
        resp = await client.get("/api/admin/answer-quality/queue")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_review_submit_requires_admin(client):
    resp = await client.post(
        "/api/admin/answer-quality/reviews",
        json={"message_id": 1, "verdict": "good"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_review_stats_requires_admin(client):
    resp = await client.get("/api/admin/answer-quality/reviews/stats")
    assert resp.status_code in (401, 403)


# --- DB-backed queue/review tests (in-memory SQLite) ---


@pytest_asyncio.fixture
async def aq_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in (ChatSession, ChatMessage, AnswerReview):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_turn(s, *, question, answer, sources, feedback=None):
    """Insert a user question + assistant answer that share one created_at, the
    way the chat save path does (single transaction, equal server-side now())."""
    ts = datetime.now(UTC)
    session = ChatSession(user_id=None)
    s.add(session)
    await s.flush()
    s.add(
        ChatMessage(
            session_id=session.id, role="user", content=question, created_at=ts
        )
    )
    assistant = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        sources=sources,
        feedback=feedback,
        created_at=ts,
    )
    s.add(assistant)
    await s.commit()
    return assistant.id


@pytest.mark.anyio
async def test_queue_pairs_question_on_equal_timestamp(aq_session):
    # C1 regression: question must be paired even though user+assistant share
    # an identical created_at (single-turn session).
    await _seed_turn(
        aq_session,
        question="什么是五蕴？",
        answer="正常长度的回答内容" * 5,
        sources=[{"text_id": 1, "juan_num": 1, "chunk_text": "x", "score": 0.2}],
    )
    res = await build_bad_answer_queue(aq_session)
    assert res["total_unreviewed"] == 1
    item = res["items"][0]
    assert item["question"] == "什么是五蕴？"
    assert "weak_evidence" in item["reason_tags"]


@pytest.mark.anyio
async def test_no_citation_item_serializes_without_sources(aq_session):
    # I3 regression: a None-sources answer must not break the queue.
    await _seed_turn(
        aq_session, question="问", answer="正常长度的回答内容" * 5, sources=None
    )
    res = await build_bad_answer_queue(aq_session)
    assert res["total_unreviewed"] == 1
    assert res["items"][0]["sources"] == []
    assert "no_citation" in res["items"][0]["reason_tags"]


@pytest.mark.anyio
async def test_queue_can_filter_by_multiple_reason_tags(aq_session):
    await _seed_turn(
        aq_session,
        question="问一",
        answer="短答",
        sources=[{"text_id": 1, "juan_num": 1, "chunk_text": "x", "score": 0.9}],
    )
    await _seed_turn(
        aq_session,
        question="问二",
        answer="正常长度的回答内容" * 5,
        sources=None,
    )
    await _seed_turn(
        aq_session,
        question="问三",
        answer="正常长度的回答内容" * 5,
        sources=[{"text_id": 1, "juan_num": 1, "chunk_text": "x", "score": 0.9}],
    )

    res = await build_bad_answer_queue(aq_session, category="abnormal,no_citation")

    assert res["total_unreviewed"] == 2
    assert {item["question"] for item in res["items"]} == {"问一", "问二"}


@pytest.mark.anyio
async def test_failed_answers_excluded_from_queue(aq_session):
    # Error-string and empty answers are bugs, not reviewable — never queued.
    await _seed_turn(
        aq_session,
        question="问一",
        answer="抱歉，AI 服务暂时不可用，请稍后重试。",
        sources=None,
    )
    await _seed_turn(aq_session, question="问二", answer="", sources=None)
    res = await build_bad_answer_queue(aq_session)
    assert res["total_unreviewed"] == 0


@pytest.mark.anyio
async def test_review_removes_item_and_snapshots(aq_session):
    mid = await _seed_turn(
        aq_session,
        question="问",
        answer="一段正常但无引经的回答" * 2,
        sources=None,
        feedback="down",
    )
    before = await build_bad_answer_queue(aq_session)
    assert before["total_unreviewed"] == 1

    remaining = await upsert_review(
        aq_session,
        message_id=mid,
        verdict="bad",
        failure_category="recall",
        note="n",
        reviewed_by=None,
    )
    assert remaining == 0

    after = await build_bad_answer_queue(aq_session)
    assert after["total_unreviewed"] == 0

    row = (
        await aq_session.execute(
            select(AnswerReview).where(AnswerReview.message_id == mid)
        )
    ).scalar_one()
    assert row.verdict == "bad"
    assert row.failure_category == "recall"
    assert row.suspicion_score > 0
    assert set(row.detection_reasons) >= {"downvoted", "no_citation"}


@pytest.mark.anyio
async def test_chat_save_guard_skips_failed_answers(aq_session):
    # The chat-side guard in _save_messages must not persist failed/empty
    # generations (neither the user nor the assistant turn).
    from app.services.chat import _save_messages

    session = ChatSession(user_id=None)
    aq_session.add(session)
    await aq_session.flush()

    assert (
        await _save_messages(
            aq_session, session.id, "问", "抱歉，AI 服务暂时不可用，请稍后重试。", []
        )
        is None
    )
    assert await _save_messages(aq_session, session.id, "问", "", []) is None
    mid = await _save_messages(
        aq_session, session.id, "问", "一段正常的佛学回答内容，解释五蕴。", []
    )
    assert mid is not None

    # only the one real turn persisted (user + assistant = 2 rows)
    rows = (await aq_session.execute(select(ChatMessage))).scalars().all()
    assert len(rows) == 2


def test_failed_answer_prefixes_match_chat():
    # The prefix set is duplicated in chat.py (save guard) and answer_quality.py
    # (queue filter); they must stay identical or legacy-junk filtering drifts.
    from app.services import answer_quality as aq
    from app.services import chat

    assert chat._FAILED_ANSWER_PREFIXES == aq._FAILED_ANSWER_PREFIXES
