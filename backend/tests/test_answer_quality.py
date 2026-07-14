"""Answer-quality queue — pure classifier unit tests + API tests."""

import warnings
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.answer_review import AnswerReview
from app.models.chat import ChatAnswerDiagnostic, ChatMessage, ChatSession
from app.schemas.admin import AnswerReviewCreate
from app.services.answer_quality import (
    WEAK_EVIDENCE_THRESHOLD,
    DiagnosticSignals,
    _is_failed_answer,
    _percentiles,
    build_bad_answer_queue,
    classify_answer,
    count_unreviewed,
    upsert_review,
)


def _sources(*scores):
    return [{"text_id": 1, "juan_num": 1, "chunk_text": "x", "score": s} for s in scores]


def _diag(
    citation_count=1,
    source_count=3,
    quote_mutation_count=0,
    citation_mutation_count=0,
    max_source_score=0.9,
):
    return DiagnosticSignals(
        citation_count=citation_count,
        source_count=source_count,
        quote_mutation_count=quote_mutation_count,
        citation_mutation_count=citation_mutation_count,
        max_source_score=max_source_score,
    )


_OK_ANSWER = "一段足够长的正常回答内容" * 3


def test_strong_answer_is_not_suspect():
    tags, score = classify_answer(_OK_ANSWER, None, _diag())
    assert tags == []
    assert score == 0.0


def test_chitchat_without_sources_is_not_suspect():
    """本来就不需要引经的问题(闲聊/元问题):回答没引用、也没来源 —— 不再是差答案。
    这正是旧 no_citation 判据制造 715 条噪音的地方。"""
    tags, score = classify_answer(
        _OK_ANSWER, None, _diag(citation_count=0, source_count=0, max_source_score=None)
    )
    assert tags == []
    assert score == 0.0


def test_fabricated_citation_is_flagged():
    """回答引了经,却一条来源都没有 —— 凭空引用。"""
    tags, score = classify_answer(
        _OK_ANSWER, None, _diag(citation_count=2, source_count=0, max_source_score=None)
    )
    assert tags == ["fabricated_citation"]
    assert score == 4.0


def test_quote_relaxed_is_flagged():
    tags, score = classify_answer(_OK_ANSWER, None, _diag(quote_mutation_count=1))
    assert tags == ["quote_relaxed"]
    assert score == 3.0


def test_citation_corrected_is_flagged():
    tags, score = classify_answer(_OK_ANSWER, None, _diag(citation_mutation_count=2))
    assert tags == ["citation_corrected"]
    assert score == 2.0


def test_downvoted_is_flagged():
    tags, score = classify_answer(_OK_ANSWER, "down", _diag())
    assert tags == ["downvoted"]
    assert score == 5.0


def test_short_answer_is_flagged_as_abnormal():
    tags, score = classify_answer("不知道", None, _diag())
    assert tags == ["abnormal"]
    assert score == 3.0


def test_weak_evidence_is_flagged_and_graded():
    """梯度沿用生产原公式 1.0 + min(gap, 0.5) * 2.0(gap = 阈值 - 来源分)。"""
    near, score_near = classify_answer(
        _OK_ANSWER, None, _diag(max_source_score=WEAK_EVIDENCE_THRESHOLD - 0.01)
    )
    far, score_far = classify_answer(_OK_ANSWER, None, _diag(max_source_score=0.01))
    assert near == ["weak_evidence"] and far == ["weak_evidence"]
    assert score_near == 1.02   # 1.0 + 0.01 * 2
    assert score_far == 1.72    # 1.0 + 0.36 * 2


def test_multiple_detectors_stack():
    tags, score = classify_answer(
        "太短", "down", _diag(citation_count=1, source_count=0, quote_mutation_count=1)
    )
    assert set(tags) == {"downvoted", "abnormal", "fabricated_citation", "quote_relaxed"}
    assert score == 5.0 + 3.0 + 4.0 + 3.0


def test_no_citation_tag_is_gone():
    """旧判据已删除:任何输入都不该再产出 no_citation。"""
    tags, _ = classify_answer(
        _OK_ANSWER, None, _diag(citation_count=0, source_count=0, max_source_score=None)
    )
    assert "no_citation" not in tags


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
        for model in (ChatSession, ChatMessage, AnswerReview, ChatAnswerDiagnostic):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_turn(s, *, question, answer, sources, feedback=None, diag: dict | None = None):
    """Insert a user question + assistant answer that share one created_at, the
    way the chat save path does (single transaction, equal server-side now()).

    ``diag=None`` = 没有诊断行 = 2026-07-01 之前的老消息(证据已被
    verify_quoted_content 在入库前抹平,不可追溯)。"""
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
    await s.flush()
    if diag is not None:
        s.add(
            ChatAnswerDiagnostic(
                message_id=assistant.id, trust_state="verified", **diag
            )
        )
    await s.commit()
    return assistant.id


def _diag_row(
    citation_count=1,
    source_count=3,
    quote_mutation_count=0,
    citation_mutation_count=0,
    max_source_score=0.9,
):
    return dict(
        citation_count=citation_count,
        source_count=source_count,
        quote_mutation_count=quote_mutation_count,
        citation_mutation_count=citation_mutation_count,
        max_source_score=max_source_score,
    )


@pytest.mark.anyio
async def test_queue_pairs_question_on_equal_timestamp(aq_session):
    # C1 regression: question must be paired even though user+assistant share
    # an identical created_at (single-turn session).
    await _seed_turn(
        aq_session,
        question="什么是五蕴？",
        answer="正常长度的回答内容" * 5,
        sources=[{"text_id": 1, "juan_num": 1, "chunk_text": "x", "score": 0.2}],
        diag=_diag_row(source_count=1, max_source_score=0.2),
    )
    res = await build_bad_answer_queue(aq_session)
    assert res["total_unreviewed"] == 1
    item = res["items"][0]
    assert item["question"] == "什么是五蕴？"
    assert "weak_evidence" in item["reason_tags"]


@pytest.mark.anyio
async def test_fabricated_citation_item_serializes_without_sources(aq_session):
    # I3 regression: a None-sources answer must not break the queue. Under the
    # new judged criteria, "sources=None + citations claimed" is
    # fabricated_citation (the old no_citation tag is gone).
    await _seed_turn(
        aq_session,
        question="问",
        answer="正常长度的回答内容" * 5,
        sources=None,
        diag=_diag_row(citation_count=2, source_count=0, max_source_score=None),
    )
    res = await build_bad_answer_queue(aq_session)
    assert res["total_unreviewed"] == 1
    assert res["items"][0]["sources"] == []
    assert "fabricated_citation" in res["items"][0]["reason_tags"]


@pytest.mark.anyio
async def test_queue_can_filter_by_multiple_reason_tags(aq_session):
    await _seed_turn(
        aq_session,
        question="问一",
        answer="短答",
        sources=[{"text_id": 1, "juan_num": 1, "chunk_text": "x", "score": 0.9}],
        diag=_diag_row(source_count=1, max_source_score=0.9),
    )
    await _seed_turn(
        aq_session,
        question="问二",
        answer="正常长度的回答内容" * 5,
        sources=None,
        diag=_diag_row(citation_count=2, source_count=0, max_source_score=None),
    )
    await _seed_turn(
        aq_session,
        question="问三",
        answer="正常长度的回答内容" * 5,
        sources=[{"text_id": 1, "juan_num": 1, "chunk_text": "x", "score": 0.9}],
        diag=_diag_row(source_count=1, max_source_score=0.9),
    )

    res = await build_bad_answer_queue(aq_session, category="abnormal,fabricated_citation")

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
        diag=_diag_row(citation_count=0, source_count=0, max_source_score=None),
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
    assert set(row.detection_reasons) >= {"downvoted"}


@pytest.mark.anyio
async def test_upsert_review_snapshots_new_tags_and_returns_cheap_count(aq_session):
    mid = await _seed_turn(
        aq_session,
        question="问",
        answer=_OK_ANSWER,
        sources=None,
        diag=_diag_row(citation_count=1, source_count=0, max_source_score=None),
    )
    remaining = await upsert_review(
        aq_session,
        message_id=mid,
        verdict="bad",
        failure_category="hallucination",
        note=None,
        reviewed_by=1,
    )
    assert remaining == 0  # 唯一一条已复核
    row = (
        await aq_session.execute(
            select(AnswerReview).where(AnswerReview.message_id == mid)
        )
    ).scalar_one()
    assert row.detection_reasons == ["fabricated_citation"]
    assert row.suspicion_score == 4.0


@pytest.mark.anyio
async def test_upsert_review_rejects_message_without_diagnostic(aq_session):
    mid = await _seed_turn(
        aq_session, question="问", answer=_OK_ANSWER, sources=None, diag=None,
    )
    with pytest.raises(ValueError):
        await upsert_review(
            aq_session,
            message_id=mid,
            verdict="good",
            failure_category=None,
            note=None,
            reviewed_by=1,
        )


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


@pytest.mark.anyio
async def test_message_without_diagnostic_never_enters_queue(aq_session):
    """7/1 之前的老消息没有诊断行 —— 证据已在入库时销毁,不可追溯,必须排除。
    即便它同时命中 downvoted + abnormal 也不能进队列。"""
    await _seed_turn(
        aq_session, question="q", answer="太短", sources=_sources(0.9),
        feedback="down", diag=None,
    )
    result = await build_bad_answer_queue(aq_session)
    assert result["total_unreviewed"] == 0
    assert result["items"] == []


@pytest.mark.anyio
async def test_clean_answer_with_diagnostic_is_not_queued(aq_session):
    await _seed_turn(
        aq_session, question="q", answer=_OK_ANSWER, sources=_sources(0.9),
        diag=_diag_row(),
    )
    result = await build_bad_answer_queue(aq_session)
    assert result["total_unreviewed"] == 0


@pytest.mark.anyio
async def test_chitchat_without_sources_is_not_queued(aq_session):
    """"what can you do today?" 这类问题:没引用、没来源 —— 不再是差答案。
    旧的 no_citation 判据正是在这里制造了 715 条噪音。"""
    await _seed_turn(
        aq_session, question="what can you do today?", answer=_OK_ANSWER, sources=None,
        diag=_diag_row(citation_count=0, source_count=0, max_source_score=None),
    )
    result = await build_bad_answer_queue(aq_session)
    assert result["total_unreviewed"] == 0


@pytest.mark.anyio
async def test_fabricated_citation_enters_queue_with_tag(aq_session):
    mid = await _seed_turn(
        aq_session, question="q", answer=_OK_ANSWER, sources=None,
        diag=_diag_row(citation_count=2, source_count=0, max_source_score=None),
    )
    result = await build_bad_answer_queue(aq_session)
    assert result["total_unreviewed"] == 1
    assert result["items"][0]["message_id"] == mid
    assert result["items"][0]["reason_tags"] == ["fabricated_citation"]
    assert result["tag_distribution"]["fabricated_citation"] == 1


@pytest.mark.anyio
async def test_queue_orders_by_suspicion_desc(aq_session):
    weak = await _seed_turn(
        aq_session, question="q1", answer=_OK_ANSWER, sources=_sources(0.30),
        diag=_diag_row(source_count=1, max_source_score=0.30),
    )  # weak_evidence ≈ 1.14
    downvoted = await _seed_turn(
        aq_session, question="q2", answer=_OK_ANSWER, sources=_sources(0.9),
        feedback="down", diag=_diag_row(),
    )  # 5.0
    result = await build_bad_answer_queue(aq_session)
    ids = [it["message_id"] for it in result["items"]]
    assert ids == [downvoted, weak]


@pytest.mark.anyio
async def test_limit_offset_pushed_down_and_total_consistent(aq_session):
    for i in range(3):
        await _seed_turn(
            aq_session, question=f"q{i}", answer=_OK_ANSWER, sources=None,
            diag=_diag_row(citation_count=1, source_count=0, max_source_score=None),
        )
    page = await build_bad_answer_queue(aq_session, limit=2, offset=0)
    assert page["total_unreviewed"] == 3      # total 是全量,不是本页
    assert len(page["items"]) == 2            # 本页只有 2 条
    tail = await build_bad_answer_queue(aq_session, limit=2, offset=2)
    assert len(tail["items"]) == 1


@pytest.mark.anyio
async def test_count_unreviewed_matches_queue_total(aq_session):
    await _seed_turn(
        aq_session, question="q", answer=_OK_ANSWER, sources=None,
        diag=_diag_row(citation_count=1, source_count=0, max_source_score=None),
    )
    assert await count_unreviewed(aq_session) == 1


@pytest.mark.anyio
async def test_abnormal_sql_matches_python_strip_on_newlines(aq_session):
    """回归测试:19 个可见字符 + 11 个换行。Python 的 .strip() 剥掉所有空白,
    trim 后长度 19 < 20 => abnormal;SQL 的 TRIM() 若只剥空格,trim 后长度仍是
    30,不会判 abnormal —— 消息会从队列/计数里静默漏掉,且一旦还命中别的标签,
    SQL 排序分会比 Python 算出的显示分少 3.0(abnormal 的权重),排序与显示就
    不一致了。这条断言锁死"SQL 排序分 == 页面显示分"。"""
    answer = "可见字符一二三四五六七八九十一二三四五" + "\n" * 11
    assert len(answer.strip()) == 19
    assert len(answer) == 30

    mid = await _seed_turn(
        aq_session,
        question="q",
        answer=answer,
        sources=None,
        diag=_diag_row(citation_count=0, source_count=0, max_source_score=None),
    )

    result = await build_bad_answer_queue(aq_session)
    assert result["total_unreviewed"] == 1

    item = result["items"][0]
    assert item["message_id"] == mid
    assert "abnormal" in item["reason_tags"]

    expected_tags, expected_score = classify_answer(
        answer, None, _diag(citation_count=0, source_count=0, max_source_score=None)
    )
    assert item["reason_tags"] == expected_tags
    assert item["suspicion_score"] == expected_score


@pytest.mark.anyio
async def test_unknown_category_matches_nothing(aq_session):
    """category 传入的片段全都不在 TAG_PREDICATES 里 —— 必须匹配不到任何行
    (不能静默退化成"匹配全部"),也不能触发 or_() 零参数的 SADeprecationWarning。"""
    await _seed_turn(
        aq_session, question="q", answer="太短", sources=None,
        feedback="down", diag=_diag_row(),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = await build_bad_answer_queue(aq_session, category="bogus")
    assert result["total_unreviewed"] == 0
    assert result["items"] == []
