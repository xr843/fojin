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
    _resolve_title,
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
async def test_multiple_candidates_picks_first_deterministically():
    """Famous sutras have multiple translator-rows under the same title
    (心经×4, 金刚经×6). The query orders by (source_id, id) so
    candidates[0] is the canonical translation; precise retrieval
    must use that rather than punt to vector — punting is the bug
    this PR is fixing."""
    db = MagicMock()
    canonical = MagicMock()
    canonical.id = 9
    canonical.title_zh = "般若波羅蜜多心經"
    canonical.lang = "lzh"
    canonical.source_id = 1
    canonical.translator = "玄奘"

    other = MagicMock()
    other.id = 6504
    other.title_zh = "般若波羅蜜多心經"
    other.lang = "lzh"
    other.source_id = 1
    other.translator = "般若共利言等"

    tc = MagicMock()
    tc.text_id = 9
    tc.juan_num = 1
    tc.content = "般若波羅蜜多。"
    tc.lang = "lzh"

    text_result = MagicMock()
    text_result.scalars = MagicMock(return_value=iter([canonical, other]))
    content_result = MagicMock()
    content_result.scalar_one_or_none = MagicMock(return_value=tc)
    db.execute = AsyncMock(side_effect=[text_result, content_result])

    result = await try_precise_text_retrieval(db, "《般若波羅蜜多心經》第1卷")
    assert result is not None
    assert result[0].text_id == 9  # canonical (玄奘) wins via SQL ORDER BY


# ──────────────────────────────────────────────────────────────────────
# Title resolution: aliases + 简→繁 normalization
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Common short names — both simplified and traditional must
        # resolve to the same canonical traditional title that lives in
        # the production DB.
        ("心经", "般若波羅蜜多心經"),
        ("心經", "般若波羅蜜多心經"),
        ("金刚经", "金剛般若波羅蜜經"),
        ("金剛經", "金剛般若波羅蜜經"),
        ("楞严经", "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經"),
        ("楞嚴經", "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經"),
        ("法华经", "妙法蓮華經"),
        ("华严经", "大方廣佛華嚴經"),
        ("圆觉经", "大方廣圓覺修多羅了義經"),
        ("涅槃经", "大般涅槃經"),
        ("起信论", "大乘起信論"),
        # Whitespace must not affect resolution.
        (" 心经 ", "般若波羅蜜多心經"),
    ],
)
def test_resolve_title_aliases(raw, expected):
    assert _resolve_title(raw) == expected


def test_resolve_title_falls_back_to_simplified_to_traditional():
    """Titles not in the alias table get OpenCC s2t conversion. This
    handles the long tail of less-common scriptures the user might
    type in simplified script (e.g. 楞伽阿跋多罗宝经 →
    楞伽阿跋多羅寶經) without each one needing a hand-curated entry."""
    # 楞伽阿跋多罗宝经 contains chars that differ across encodings
    # (罗→羅, 宝→寶); s2t should convert them.
    out = _resolve_title("楞伽阿跋多罗宝经")
    assert "羅" in out
    assert "寶" in out


def test_resolve_title_passthrough_for_already_traditional():
    """A title that's already in the canonical traditional form should
    survive resolution unchanged — neither alias nor s2t should
    mangle it."""
    canonical = "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經"
    assert _resolve_title(canonical) == canonical


@pytest.mark.anyio
async def test_zero_candidates_returns_none():
    """Title doesn't resolve to any DB row — must fall back to vector
    RAG, never invent a result."""
    db = MagicMock()
    text_result = MagicMock()
    text_result.scalars = MagicMock(return_value=iter([]))
    db.execute = AsyncMock(side_effect=[text_result])
    result = await try_precise_text_retrieval(db, "《不存在经》第1卷")
    assert result is None


@pytest.mark.anyio
async def test_alias_resolution_drives_lookup_query():
    """When the user types a short alias like 《心经》第1卷, the SQL
    lookup must execute against the resolved canonical title, not the
    raw input — otherwise the alias table is purely decorative."""
    db = MagicMock()
    bt = MagicMock()
    bt.id = 9
    bt.title_zh = "般若波羅蜜多心經"
    bt.lang = "lzh"
    bt.source_id = 1
    bt.translator = "玄奘"
    tc = MagicMock()
    tc.text_id = 9
    tc.juan_num = 1
    tc.content = "般若波羅蜜多。"
    tc.lang = "lzh"
    text_result = MagicMock()
    text_result.scalars = MagicMock(return_value=iter([bt]))
    content_result = MagicMock()
    content_result.scalar_one_or_none = MagicMock(return_value=tc)
    db.execute = AsyncMock(side_effect=[text_result, content_result])

    result = await try_precise_text_retrieval(db, "《心经》第1卷")
    assert result is not None
    assert result[0].title_zh == "般若波羅蜜多心經"
    assert result[0].text_id == 9


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
    texts are in scope. Empty list, by contrast, rejects every hit —
    that's the contract callers like chat.py rely on for masters
    whose corpus index isn't loaded yet (Ajahn Chah, etc)."""
    db, _, _ = _mock_db_with_text_and_content(text_id=42)
    result = await try_precise_text_retrieval(db, "《心经》第1卷", scope_text_ids=None)
    assert result is not None


@pytest.mark.anyio
async def test_scope_text_ids_empty_list_blocks_every_hit():
    """Empty list = "this master uses full-corpus vector RAG but
    precise retrieval is disabled". This was the contract Ajahn
    Chah's master profile relied on but chat.py's falsy-coalesce
    silently broke it (an empty list collapsed to None, which means
    'unrestricted'). Production sample 2026-05-07: Ajahn Chah master
    answered `《楞严经》第一卷` with the chunk_text of 楞严经
    silently sitting in the LLM's context — the persona prose hid
    it, but the bypass was real. This test locks the empty-list
    contract so a future regression can't undo the chat.py fix."""
    db, _, _ = _mock_db_with_text_and_content(text_id=42)
    result = await try_precise_text_retrieval(db, "《心经》第1卷", scope_text_ids=[])
    assert result is None


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
