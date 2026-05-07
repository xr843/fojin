"""Tests for precise text retrieval short-circuit.

The short-circuit must be conservative — returning None on any
ambiguity is the correct behaviour because the caller falls back to
vector RAG, which is the safe default. Tests therefore emphasise the
no-trigger and no-match paths as much as the happy one.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.precise_retrieval import (
    _cjk_to_int,
    _detect_title_juan,
    _parse_juan_number,
    try_precise_text_retrieval,
)

# ──────────────────────────────────────────────────────────────────────
# CJK numeral parser
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("一", 1),
        ("九", 9),
        ("十", 10),
        ("十一", 11),
        ("十九", 19),
        ("二十", 20),
        ("二十一", 21),
        ("九十九", 99),
        ("一百", 100),
        ("一百零", None),  # malformed (零 is digit, not separator)
        ("一百一", 101),
        ("一百二十", 120),
        ("一百二十三", 123),
        ("六百", 600),  # CBETA's largest fascicle count (大般若经)
    ],
)
def test_cjk_to_int_parses_canonical_forms(raw, expected):
    assert _cjk_to_int(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "abc",
        "壹",  # uppercase form not supported (rare in queries)
        "千",  # >999 fascicles don't exist; reject as defensive
    ],
)
def test_cjk_to_int_rejects_unrecognised(raw):
    assert _cjk_to_int(raw) is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1", 1),
        ("99", 99),
        ("一", 1),
        ("十二", 12),
        (" 7 ", 7),
        ("", None),
        ("1一", None),  # mixed alphabets — refuse to guess
        ("一1", None),
    ],
)
def test_parse_juan_number(raw, expected):
    assert _parse_juan_number(raw) == expected


# ──────────────────────────────────────────────────────────────────────
# Pattern detector
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query, expected",
    [
        ("《楞严经》第一卷", ("楞严经", 1)),
        ("《心经》第1卷", ("心经", 1)),
        ("《大般若经》第600卷", ("大般若经", 600)),
        ("帮我找《楞伽经》第7卷的原文", ("楞伽经", 7)),
        ("《楞伽经合辙》第7卷指出七地非二乘可及", ("楞伽经合辙", 7)),
        ("《心经》 第 一 卷", ("心经", 1)),  # whitespace tolerated
    ],
)
def test_detect_triggers_on_explicit_title_and_juan(query, expected):
    assert _detect_title_juan(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "心经第一卷讲什么",  # missing 《》 — too loose
        "讲到《心经》怎么样",  # passing mention, no juan
        "《》第一卷",  # empty title
        "《心经》 第卷",  # missing num
        "《心经》第〇卷",  # 〇 not in numeral map
        "《心经》第零卷",  # juan=0 rejected
    ],
)
def test_detect_does_not_trigger_on_loose_or_malformed(query):
    assert _detect_title_juan(query) is None


def test_detect_returns_first_match_when_query_names_multiple():
    """If a user names two fascicles, returning the first is the
    deterministic choice; vector RAG can take the second-best path."""
    q = "《心经》第1卷与《金刚经》第3卷"
    assert _detect_title_juan(q) == ("心经", 1)


# ──────────────────────────────────────────────────────────────────────
# try_precise_text_retrieval — DB integration shape (mocked)
# ──────────────────────────────────────────────────────────────────────


def _mock_db_with_text_and_content(*, text_id=42, title="心经", lang="lzh", juan=1, content="般若波罗蜜多。"):
    """Build a minimal AsyncSession mock that returns one BuddhistText
    on the title query and one TextContent on the fascicle query."""
    db = MagicMock()

    bt = MagicMock()
    bt.id = text_id
    bt.title_zh = title
    bt.lang = lang
    bt.source_id = 5

    tc = MagicMock()
    tc.text_id = text_id
    tc.juan_num = juan
    tc.content = content
    tc.lang = lang

    text_result = MagicMock()
    text_result.scalars = MagicMock(return_value=iter([bt]))
    content_result = MagicMock()
    content_result.scalar_one_or_none = MagicMock(return_value=tc)

    db.execute = AsyncMock(side_effect=[text_result, content_result])
    return db, bt, tc


@pytest.mark.anyio
async def test_no_trigger_returns_none():
    db = MagicMock()
    db.execute = AsyncMock()  # should never be called
    result = await try_precise_text_retrieval(db, "心经讲什么")
    assert result is None
    db.execute.assert_not_called()


@pytest.mark.anyio
async def test_happy_path_returns_single_chatsource_with_real_content():
    db, _bt, _tc = _mock_db_with_text_and_content()
    result = await try_precise_text_retrieval(db, "《心经》第1卷")
    assert result is not None
    assert len(result) == 1
    src = result[0]
    assert src.text_id == 42
    assert src.juan_num == 1
    assert src.title_zh == "心经"
    assert "般若波罗蜜多" in src.chunk_text
    assert src.score == 1.0  # exact metadata hit, max confidence


@pytest.mark.anyio
async def test_truncates_long_content_with_marker():
    """A 50K-char fascicle must be cut to MAX_FASCICLE_CHUNK_CHARS so
    the LLM context budget is respected, and the truncation must be
    self-announced so the LLM doesn't claim coverage of the tail."""
    long_content = "般若" * 5000  # 10K chars
    db, _, _ = _mock_db_with_text_and_content(content=long_content)
    result = await try_precise_text_retrieval(db, "《心经》第1卷")
    assert result is not None
    chunk = result[0].chunk_text
    assert len(chunk) <= 8500  # MAX + marker headroom
    assert "未列入此次检索" in chunk


@pytest.mark.anyio
async def test_ambiguous_title_falls_back_to_none():
    """Two BuddhistText rows with the same title: don't guess; let
    vector RAG handle it via score."""
    db = MagicMock()
    bt1, bt2 = MagicMock(), MagicMock()
    text_result = MagicMock()
    text_result.scalars = MagicMock(return_value=iter([bt1, bt2]))
    db.execute = AsyncMock(side_effect=[text_result])
    result = await try_precise_text_retrieval(db, "《心经》第1卷")
    assert result is None


@pytest.mark.anyio
async def test_unknown_title_returns_none():
    db = MagicMock()
    text_result = MagicMock()
    text_result.scalars = MagicMock(return_value=iter([]))
    db.execute = AsyncMock(side_effect=[text_result])
    result = await try_precise_text_retrieval(db, "《不存在经》第1卷")
    assert result is None


@pytest.mark.anyio
async def test_known_title_but_missing_fascicle_returns_none():
    """Title is in canon, but the requested 卷 has no text_contents row
    (e.g. CBETA dump didn't include it). Falling back to vector RAG is
    safer than handing the LLM zero context."""
    db = MagicMock()
    bt = MagicMock()
    bt.id = 42
    bt.title_zh = "心经"
    bt.lang = "lzh"
    bt.source_id = 5
    text_result = MagicMock()
    text_result.scalars = MagicMock(return_value=iter([bt]))
    content_result = MagicMock()
    content_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(side_effect=[text_result, content_result])
    result = await try_precise_text_retrieval(db, "《心经》第99卷")
    assert result is None


@pytest.mark.anyio
async def test_scope_text_ids_filters_out_of_scope_hit():
    """Master mode (法师模式) restricts retrieval to a curated corpus.
    A precise hit on a text outside that corpus must be rejected, even
    when the user asks for it explicitly — the persona contract
    promises master-corpus-only context."""
    db, _, _ = _mock_db_with_text_and_content(text_id=42)
    # text_id=42 NOT in this master's allowed list
    result = await try_precise_text_retrieval(
        db, "《心经》第1卷", scope_text_ids=[100, 200, 300],
    )
    assert result is None


@pytest.mark.anyio
async def test_scope_text_ids_passes_in_scope_hit():
    db, _, _ = _mock_db_with_text_and_content(text_id=42)
    result = await try_precise_text_retrieval(
        db, "《心经》第1卷", scope_text_ids=[42, 100, 200],
    )
    assert result is not None
    assert result[0].text_id == 42


@pytest.mark.anyio
async def test_scope_text_ids_none_means_unrestricted():
    """None (the default) preserves the non-master-mode behaviour: all
    texts are in scope. Empty list, by contrast, would correctly reject
    every hit — but that's the caller's responsibility to construct."""
    db, _, _ = _mock_db_with_text_and_content(text_id=42)
    result = await try_precise_text_retrieval(db, "《心经》第1卷", scope_text_ids=None)
    assert result is not None


@pytest.mark.anyio
async def test_empty_content_returns_none():
    """A TextContent row with empty content is metadata-only; treat as
    a miss so the LLM doesn't get a blank context block."""
    db = MagicMock()
    bt = MagicMock()
    bt.id = 42
    bt.title_zh = "心经"
    bt.lang = "lzh"
    bt.source_id = 5
    tc = MagicMock()
    tc.content = ""
    tc.lang = "lzh"
    text_result = MagicMock()
    text_result.scalars = MagicMock(return_value=iter([bt]))
    content_result = MagicMock()
    content_result.scalar_one_or_none = MagicMock(return_value=tc)
    db.execute = AsyncMock(side_effect=[text_result, content_result])
    result = await try_precise_text_retrieval(db, "《心经》第1卷")
    assert result is None
