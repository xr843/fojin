from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.chat import ChatAnswerDiagnostic, ChatMessage, ChatSession
from app.schemas.chat import ChatSource
from app.services.chat_trust import build_trust_status, persist_answer_diagnostic
from app.services.citation_guard import CitationMutation
from app.services.quote_verifier import QuoteMutation


def _src(score: float = 0.91) -> ChatSource:
    return ChatSource(
        text_id=7,
        juan_num=1,
        chunk_index=3,
        chunk_text="色不异空，空不异色。",
        score=score,
        title_zh="心经",
    )


def _citation_mutation() -> CitationMutation:
    return CitationMutation(
        kind="fascicle_corrected",
        original="【《心经》第99卷】",
        replacement="【《心经》第1卷】",
        title="心经",
        original_juan=99,
        corrected_juan=1,
    )


def _quote_mutation() -> QuoteMutation:
    return QuoteMutation(
        quote="假引文假引文假引文",
        title="心经",
        juan=1,
        reason="quote_not_in_source",
    )


def test_verified_status_counts_citations_and_source_scores():
    status = build_trust_status(
        "经云：「色不异空，空不异色」【《心经》第1卷】",
        [_src(0.91), _src(0.77)],
        citation_mutations=[],
        quote_mutations=[],
    )

    assert status.state == "verified"
    assert status.citation_count == 1
    assert status.source_count == 2
    assert status.citation_mutation_count == 0
    assert status.quote_mutation_count == 0
    assert status.max_source_score == 0.91
    assert status.min_source_score == 0.77


def test_status_prioritizes_relaxed_quotes_over_corrected_citations():
    # verify_quoted_content now downgrades a non-verbatim quote, so a quote
    # mutation → the (fixed) answer is marked quote_relaxed, taking priority
    # over a citation correction.
    status = build_trust_status(
        "经云：假引文假引文假引文【《心经》第1卷】",
        [_src()],
        citation_mutations=[_citation_mutation()],
        quote_mutations=[_quote_mutation()],
    )

    assert status.state == "quote_relaxed"
    assert status.citation_mutation_count == 1
    assert status.quote_mutation_count == 1


def test_status_marks_corrected_citation_without_quote_failure():
    status = build_trust_status(
        "见【《心经》第1卷】。",
        [_src()],
        citation_mutations=[_citation_mutation()],
        quote_mutations=[],
    )

    assert status.state == "citation_corrected"
    assert status.citation_mutation_count == 1


def test_status_marks_no_sources_even_when_answer_mentions_texts():
    status = build_trust_status(
        "可参看《心经》。", [], citation_mutations=[], quote_mutations=[]
    )

    assert status.state == "no_sources"
    assert status.source_count == 0
    assert status.max_source_score is None
    assert status.min_source_score is None


@pytest_asyncio.fixture
async def trust_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in (ChatSession, ChatMessage, ChatAnswerDiagnostic):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.anyio
async def test_persist_answer_diagnostic_upserts_by_message_id(trust_session):
    session = ChatSession(user_id=None)
    trust_session.add(session)
    await trust_session.flush()
    msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content="见【《心经》第1卷】。",
        sources=[_src().model_dump()],
        created_at=datetime.now(UTC),
    )
    trust_session.add(msg)
    await trust_session.commit()
    await trust_session.refresh(msg)

    first = build_trust_status(
        msg.content,
        [_src()],
        citation_mutations=[_citation_mutation()],
        quote_mutations=[],
    )
    await persist_answer_diagnostic(
        trust_session,
        message_id=msg.id,
        trust_status=first,
        citation_mutations=[_citation_mutation()],
        quote_mutations=[],
    )

    row = (
        await trust_session.execute(
            select(ChatAnswerDiagnostic).where(ChatAnswerDiagnostic.message_id == msg.id)
        )
    ).scalar_one()
    assert row.trust_state == "citation_corrected"
    assert row.citation_count == 1
    assert row.citation_mutations[0]["kind"] == "fascicle_corrected"

    second = build_trust_status(
        msg.content, [_src()], citation_mutations=[], quote_mutations=[]
    )
    await persist_answer_diagnostic(
        trust_session,
        message_id=msg.id,
        trust_status=second,
        citation_mutations=[],
        quote_mutations=[],
    )

    rows = (
        await trust_session.execute(select(ChatAnswerDiagnostic))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].trust_state == "verified"
    assert rows[0].citation_mutations == []
