"""Tests for the alignment flywheel.

The pgvector mine needs the corpus DB, so it isn't unit-tested here (like the
eval). What IS tested: the pure candidate-selection decision (threshold / dedup /
same-text skip) and the review state machine (accept → promote into
alignment_pairs, reject, no double-review) over in-memory SQLite.
"""

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.alignment_candidate import AlignmentCandidate
from app.services.alignment_flywheel import (
    ChunkRef,
    list_pending,
    pair_key,
    propose_anchor_neighbour,
    review_candidate,
    select_new_candidates,
)


def _ref(tid, juan=1, cidx=0, lang="lzh"):
    return ChunkRef(text_id=tid, juan_num=juan, chunk_index=cidx, lang=lang)


# ── pure decision logic ──────────────────────────────────────────────────


def test_select_keeps_only_above_threshold():
    src = _ref(1)
    neighbours = [(_ref(10, lang="pi"), 0.9), (_ref(11, lang="bo"), 0.5)]
    out = select_new_candidates(src, neighbours, set(), threshold=0.62)
    assert [t[1].text_id for t in out] == [10]     # 0.5 dropped


def test_select_skips_same_text_and_existing_and_dupes():
    src = _ref(1)
    existing = {pair_key(src, _ref(20, lang="pi"))}
    neighbours = [
        (_ref(1, lang="pi"), 0.99),    # same text_id → skip
        (_ref(20, lang="pi"), 0.95),   # already known → skip
        (_ref(30, lang="pi"), 0.8),    # keep
        (_ref(30, lang="pi"), 0.8),    # duplicate in-call → skip
    ]
    out = select_new_candidates(src, neighbours, existing, threshold=0.62)
    assert [t[1].text_id for t in out] == [30]


def test_pair_key_is_directed():
    a, b = _ref(1), _ref(2)
    assert pair_key(a, b) != pair_key(b, a)


def test_propose_anchor_neighbour_offsets_both_sides():
    a = _ref(1, juan=2, cidx=5, lang="lzh")
    b = _ref(9, juan=1, cidx=3, lang="bo")
    na, nb = propose_anchor_neighbour(a, b, 1)
    assert (na.text_id, na.juan_num, na.chunk_index) == (1, 2, 6)
    assert (nb.text_id, nb.juan_num, nb.chunk_index) == (9, 1, 4)
    assert nb.lang == "bo"                                # lang preserved
    # -1 works too; going before chunk 0 is refused.
    assert propose_anchor_neighbour(a, b, -1)[1].chunk_index == 2
    assert propose_anchor_neighbour(_ref(1, cidx=0), _ref(2, cidx=5), -1) is None


# ── review state machine (SQLite) ────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(AlignmentCandidate.__table__.create)
        # Minimal alignment_pairs table — only the columns the promote inserts.
        await conn.execute(text(
            "CREATE TABLE alignment_pairs ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " text_a_id INT, text_a_juan_num INT, text_a_chunk_index INT, text_a_lang TEXT,"
            " text_b_id INT, text_b_juan_num INT, text_b_chunk_index INT, text_b_lang TEXT,"
            " confidence FLOAT, method TEXT)"
        ))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _add(db, **kw):
    defaults = dict(
        text_a_id=1, text_a_juan_num=1, text_a_chunk_index=0, text_a_lang="lzh",
        text_b_id=2, text_b_juan_num=1, text_b_chunk_index=0, text_b_lang="pi",
        similarity=0.8, source="knn-bootstrap", status="pending",
    )
    defaults.update(kw)
    c = AlignmentCandidate(**defaults)
    db.add(c)
    await db.flush()
    return c


@pytest.mark.anyio
async def test_accept_promotes_into_alignment_pairs(db):
    c = await _add(db, similarity=0.91)
    out = await review_candidate(db, c.id, accept=True, user_id=7)
    assert out.status == "accepted"
    assert out.reviewed_by == 7
    # A ground-truth alignment_pairs row now exists with method flywheel-verified.
    row = (await db.execute(text(
        "SELECT text_a_id, text_b_id, confidence, method FROM alignment_pairs"
    ))).all()
    assert len(row) == 1
    assert row[0] == (1, 2, 0.91, "flywheel-verified")


@pytest.mark.anyio
async def test_reject_does_not_promote(db):
    c = await _add(db)
    out = await review_candidate(db, c.id, accept=False, user_id=7)
    assert out.status == "rejected"
    n = (await db.execute(text("SELECT COUNT(*) FROM alignment_pairs"))).scalar()
    assert n == 0


@pytest.mark.anyio
async def test_already_reviewed_is_noop(db):
    c = await _add(db, status="accepted")
    out = await review_candidate(db, c.id, accept=True, user_id=7)
    assert out.status == "accepted"
    # No second promote row.
    n = (await db.execute(text("SELECT COUNT(*) FROM alignment_pairs"))).scalar()
    assert n == 0


@pytest.mark.anyio
async def test_missing_candidate_returns_none(db):
    assert await review_candidate(db, 9999, accept=True, user_id=1) is None


@pytest.mark.anyio
async def test_list_pending_orders_by_similarity_desc(db):
    await _add(db, text_b_id=2, similarity=0.7)
    await _add(db, text_b_id=3, similarity=0.95)
    await _add(db, text_b_id=4, similarity=0.5, status="rejected")  # excluded
    pending = await list_pending(db, limit=10)
    assert [c.similarity for c in pending] == [0.95, 0.7]
