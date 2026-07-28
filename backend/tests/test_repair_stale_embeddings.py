"""Candidate selection for scripts/repair_stale_embeddings.py.

Prod 2026-07-28: a user asked a 俱舍論 question and got a verbatim-correct quote
attributed to the wrong fascicle — the answer said 第13卷, the passage lives in
卷16. Cause: ``text_embeddings`` rows labelled (text 38, juan 13) hold 109 chunks
covering real juan 13→17, because an older ingest chunked a multi-juan blob and
stamped every chunk with the FIRST juan's number. ``rag_retrieval`` builds its
``[出处: 《X》第N卷]`` header from that juan_num, so the LLM is handed — and
faithfully copies — a wrong fascicle.

Why it survived: the repair pass only ever looked for juans embedded to LESS
than their content (``e < ratio * c``). A juan embedded to 6.8x its content is
the same corruption seen from the other side, and the predicate is false for it,
so the script skipped it forever. ``generate_embeddings`` can't fix it either —
``ON CONFLICT DO NOTHING`` never overwrites an existing chunk.

The tests below pin BOTH halves of the detector. The ratio is only a prefilter:
on prod it flagged 1,881 juans where the containment test confirmed 1,020. The
861-juan difference is densely-chunked-but-intact, and re-embedding those would
renumber chunk_index and break alignment references for texts that were fine —
hence test_leaves_densely_chunked_juan_alone, which the ratio alone fails.
"""

import pytest
import pytest_asyncio
from scripts.repair_stale_embeddings import _find_candidates
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.chat import TextEmbedding
from app.models.text import BuddhistText, TextContent

# Varied CJK so a 40-char needle is distinctive — a uniform "字"*N body would
# make every containment probe match by accident.
BODY = "".join(chr(0x4E00 + (i * 7) % 8000) for i in range(9000))
FOREIGN = "".join(chr(0x4E00 + (i * 11 + 3) % 8000) for i in range(9000))


def _slices(body: str, stride: int, size: int = 500) -> list[str]:
    return [body[i : i + size] for i in range(0, len(body), stride)]


@pytest_asyncio.fixture
async def conn():
    """One juan per interesting shape, all with a 9,000-char body but the stub.

    Real chunking is chunk_size=500 / overlap=50 → stride 450, so a HEALTHY juan
    embeds to ~500/450 = 1.11x its content. Any upper bound must clear that.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as c:
        for model in (BuddhistText, TextContent, TextEmbedding):
            await c.run_sync(model.__table__.create)
        for tid in (1, 2, 3, 4, 5):
            await c.execute(
                sql_text("INSERT INTO buddhist_texts (id, cbeta_id, title_zh, lang) "
                         "VALUES (:i, :c, '測試經', 'lzh')"),
                {"i": tid, "c": f"T{tid:04d}"},
            )

        async def add(tid, jn, body, chunks):
            await c.execute(
                sql_text("INSERT INTO text_contents (text_id, juan_num, content, lang, char_count) "
                         "VALUES (:t, :j, :body, 'lzh', :n)"),
                {"t": tid, "j": jn, "body": body, "n": len(body)},
            )
            if chunks:
                await c.execute(
                    sql_text("INSERT INTO text_embeddings "
                             "(text_id, juan_num, chunk_index, chunk_text) "
                             "VALUES (:t, :j, :i, :x)"),
                    [{"t": tid, "j": jn, "i": i, "x": x} for i, x in enumerate(chunks)],
                )

        # 1: healthy — stride 450, every chunk inside its own body (1.11x)
        await add(1, 1, BODY, _slices(BODY, 450))
        # 2: under-embedded — a truncated pre-parser-fix parse (0.22x)
        await add(2, 1, BODY, _slices(BODY, 450)[:4])
        # 3: over-embedded AND spilled — chunks continue into the NEXT juan's
        #    text under this juan's number. The 俱舍論 shape.
        await add(3, 13, BODY, _slices(BODY, 450) + _slices(FOREIGN, 450))
        # 4: content stub — below min_content, must be left alone
        await add(4, 1, "文" * 100, _slices(BODY, 450))
        # 5: over-embedded but INTACT — denser stride, nothing past the end (2.2x)
        await add(5, 1, BODY, _slices(BODY, 225))
    async with engine.connect() as c:
        yield c
    await engine.dispose()


async def _keys(conn, over_ratio: float = 1.3):
    cands = await _find_candidates(
        conn, ratio=0.9, min_content=500, over_ratio=over_ratio
    )
    return {(t, j) for t, j, _c, _e in cands}


@pytest.mark.asyncio
async def test_flags_spilled_juan(conn):
    """The regression this file exists for: chunks running past the juan they are
    filed under. Nothing is *missing*, so the old one-sided predicate missed it."""
    assert (3, 13) in await _keys(conn)


@pytest.mark.asyncio
async def test_still_flags_under_embedded_juan(conn):
    """The original behaviour must survive — this is what fixed T0279 juan 1."""
    assert (2, 1) in await _keys(conn)


@pytest.mark.asyncio
async def test_leaves_healthy_juan_alone(conn):
    """1.11x is what correct chunking produces; re-embedding ~9,000 healthy juans
    would burn the embedding API for nothing."""
    assert (1, 1) not in await _keys(conn)


@pytest.mark.asyncio
async def test_leaves_densely_chunked_juan_alone(conn):
    """2.2x embedded but every chunk still inside its own juan — an old, denser
    chunking that is self-consistent. Its alignment_pairs / mitra_alignments rows
    reference that chunk_index scheme, so re-embedding would break cross-canon
    alignment for a text that was never broken. Ratio alone flags this; only the
    containment test spares it."""
    assert (5, 1) not in await _keys(conn)


@pytest.mark.asyncio
async def test_leaves_content_stub_alone(conn):
    """Prod has juans whose text_contents is a stub of a few dozen chars (閑居編
    X0949 etc.) against normal embeddings. There the CONTENT is broken, not the
    vectors, and re-embedding would delete real chunks to write back almost
    nothing. min_content is the only guard against that data loss."""
    assert (4, 1) not in await _keys(conn)


@pytest.mark.asyncio
async def test_over_ratio_gates_the_containment_check(conn):
    """The containment test is the judge, but the ratio still decides who gets
    tried — raising it past the spill's size must let the spilled juan through
    untouched, so operators can narrow a run to the worst offenders."""
    assert (3, 13) not in await _keys(conn, over_ratio=50.0)
