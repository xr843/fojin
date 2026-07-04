"""Tests for eval.from_feedback — mining prod failures into eval candidates.

Uses an in-memory async SQLite DB (same pattern as test_answer_quality) so the
real SQL runs, including the shared-timestamp question pairing.
"""

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from eval.from_feedback import collect_feedback_candidates
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.answer_review import AnswerReview
from app.models.chat import ChatMessage, ChatSession


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in (ChatSession, ChatMessage, AnswerReview):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_turn(s, *, question, answer, sources=None, feedback=None, ts=None):
    """User question + assistant answer sharing one created_at, as the chat
    save path does. Returns the assistant message id."""
    ts = ts or datetime.now(UTC)
    session = ChatSession(user_id=None)
    s.add(session)
    await s.flush()
    s.add(ChatMessage(session_id=session.id, role="user", content=question, created_at=ts))
    assistant = ChatMessage(
        session_id=session.id, role="assistant", content=answer,
        sources=sources, feedback=feedback, created_at=ts,
    )
    s.add(assistant)
    await s.commit()
    return assistant.id


async def test_downvote_and_admin_bad_surface_good_excluded(db):
    down_id = await _seed_turn(
        db, question="什么是缘起？", answer="胡说八道的答案",
        sources=[{"title_zh": "杂阿含经"}, {"title_zh": "中阿含经"}], feedback="down",
    )
    bad_id = await _seed_turn(db, question="心经的作者是谁？", answer="错误答案")
    db.add(AnswerReview(message_id=bad_id, verdict="bad", failure_category="recall"))
    # A good answer with no negative signal must NOT surface.
    await _seed_turn(db, question="四圣谛是什么？", answer="正确答案", feedback="up")
    # An admin "good" verdict must NOT surface either.
    good_id = await _seed_turn(db, question="八正道？", answer="也不错")
    db.add(AnswerReview(message_id=good_id, verdict="good"))
    await db.commit()

    cands = await collect_feedback_candidates(db, window_days=90, limit=200)

    by_mid = {c["message_id"]: c for c in cands}
    assert set(by_mid) == {down_id, bad_id}, "only downvoted + admin-bad surface"

    down = by_mid[down_id]
    assert down["candidate_id"] == f"fb-{down_id}"
    assert down["question"] == "什么是缘起？"  # paired despite equal timestamp
    assert down["signals"] == ["user_downvote"]
    assert down["failure_category"] is None
    assert down["observed_sources"] == ["杂阿含经", "中阿含经"]
    assert down["curate"] == {
        "category": None, "reference_sources": [], "reference_answer_points": [],
    }

    bad = by_mid[bad_id]
    assert bad["signals"] == ["admin_bad"]
    assert bad["failure_category"] == "recall"


async def test_both_signals_merge_into_one_candidate(db):
    mid = await _seed_turn(
        db, question="重复问题", answer="坏答案", feedback="down",
    )
    db.add(AnswerReview(message_id=mid, verdict="bad", failure_category="hallucination"))
    await db.commit()

    cands = await collect_feedback_candidates(db)
    assert len(cands) == 1
    c = cands[0]
    assert c["signals"] == ["user_downvote", "admin_bad"]  # both, one entry
    assert c["failure_category"] == "hallucination"


async def test_window_days_excludes_old_and_orders_recent_first(db):
    now = datetime.now(UTC)
    old = await _seed_turn(
        db, question="旧问题", answer="旧坏答案", feedback="down",
        ts=now - timedelta(days=120),
    )
    recent = await _seed_turn(
        db, question="新问题", answer="新坏答案", feedback="down",
        ts=now - timedelta(days=1),
    )

    cands = await collect_feedback_candidates(db, window_days=90)
    mids = [c["message_id"] for c in cands]
    assert old not in mids  # outside window
    assert mids == [recent]

    # Widen the window: both appear, most-recent first.
    cands_all = await collect_feedback_candidates(db, window_days=365)
    assert [c["message_id"] for c in cands_all] == [recent, old]


async def test_admin_bad_ignores_window_via_message_but_still_recent(db):
    # An admin-bad message older than the window is still gated by created_at
    # (the query filters messages by window); this documents that behavior.
    old_bad = await _seed_turn(
        db, question="旧的坏答案", answer="x",
        ts=datetime.now(UTC) - timedelta(days=200),
    )
    db.add(AnswerReview(message_id=old_bad, verdict="bad"))
    await db.commit()

    assert await collect_feedback_candidates(db, window_days=90) == []
    assert len(await collect_feedback_candidates(db, window_days=365)) == 1
