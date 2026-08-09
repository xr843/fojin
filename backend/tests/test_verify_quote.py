"""Open-world quote verification (services/quote_lookup + /api/verify/quote).

Service-level tests with fake DB/ES doubles — no network, no real ES. The
contract under test:

- ES only shortlists; the verdict comes from the normalised substring test.
- juan_matched honesty: a hit in a different juan than hinted must NOT count
  as cite confirmation (the chat pipeline's any-juan fallback is a known
  fascicle-accuracy leak the public API must not inherit).
- windowed_best_span must agree with quote_verifier._windowed_ratio, since it
  re-implements the same windowing to add span output.
"""

import sys
from unittest.mock import MagicMock

import pytest

# Ensure elasticsearch stub exists before any app import (test_kg.py pattern).
if "elasticsearch" not in sys.modules:
    _es_stub = MagicMock()
    _es_stub.AsyncElasticsearch = MagicMock
    sys.modules["elasticsearch"] = _es_stub

from app.config import settings
from app.core.rate_limit import STRICT_PATHS
from app.services.quote_lookup import (
    QuoteTooShortError,
    diff_ops,
    verify_quote,
    windowed_best_span,
)
from app.services.quote_verifier import _windowed_ratio, normalise_for_match

# 雪山偈 — long enough to clear MIN_QUOTE_CHARS after normalisation.
SNOW_VERSE = "諸行無常，是生滅法，生滅滅已，寂滅為樂"
JUAN_13 = f"爾時世尊而說偈言：{SNOW_VERSE}。是時獵師聞偈歡喜。"
JUAN_16 = f"復次善男子，{SNOW_VERSE}，是名大涅槃義。"
JUAN_OTHER = "如是我聞，一時佛在王舍城耆闍崛山中，與大比丘眾俱。"


# ── fakes ────────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeDB:
    """Routes the service's raw SQL by prefix onto in-memory fixtures."""

    def __init__(self, texts, contents):
        # texts: {text_id: (cbeta_id, title_zh)}; contents: {(text_id, juan): str}
        self.texts = texts
        self.contents = contents

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        if not p and hasattr(statement, "compile"):
            # ORM select() carries its bound values inside the statement.
            p = statement.compile().params
        if sql.startswith("SELECT id FROM buddhist_texts WHERE cbeta_id"):
            rows = [(tid,) for tid, (cb, _) in self.texts.items() if cb == p["c"]]
            return _Result(sorted(rows)[:1])
        if sql.startswith("SELECT buddhist_texts.id FROM buddhist_texts"):
            # ORM-compiled form used by services.text.get_text_id_by_cbeta
            # (the URN cite-hint path).
            cb_wanted = p.get("cbeta_id_1")
            rows = [(tid,) for tid, (cb, _) in self.texts.items() if cb == cb_wanted]

            class _Scalar(_Result):
                def scalar_one_or_none(self):
                    return self._rows[0][0] if self._rows else None

            return _Scalar(sorted(rows)[:1])
        if sql.startswith("SELECT cbeta_id, title_zh FROM buddhist_texts"):
            t = self.texts.get(p["t"])
            return _Result([t] if t else [])
        if sql.startswith("SELECT cbeta_id FROM buddhist_texts"):
            t = self.texts.get(p["t"])
            return _Result([(t[0],)] if t else [])
        if sql.startswith("SELECT content FROM text_contents"):
            body = self.contents.get((p["t"], p["j"]))
            return _Result([(body,)] if body is not None else [])
        if sql.startswith("SELECT COUNT(*) FROM text_contents"):
            n = sum(1 for (tid, _j) in self.contents if tid == p["t"])
            return _Result([(n,)])
        if sql.startswith("SELECT juan_num, content FROM text_contents"):
            rows = sorted(
                (j, body) for (tid, j), body in self.contents.items() if tid == p["t"]
            )
            return _Result(rows)
        raise AssertionError(f"unrouted SQL in test double: {sql}")


class FakeES:
    def __init__(self, hits_by_type=None):
        # hits_by_type: {"match_phrase": [...], "match": [...]}
        self.hits_by_type = hits_by_type or {}
        self.calls = []

    async def search(self, index, body):
        self.calls.append(body)
        (qtype,) = body["query"]["bool"]["must"][0].keys()
        hits = self.hits_by_type.get(qtype, [])
        # Honour the text_id term filter like real ES would.
        for f in body["query"]["bool"]["filter"]:
            if "term" in f and "text_id" in f["term"]:
                hits = [h for h in hits if h["text_id"] == f["term"]["text_id"]]
        return {"hits": {"hits": [{"_source": h} for h in hits]}}


def _hit(text_id, juan, cbeta="T0374", title="大般涅槃經"):
    return {"text_id": text_id, "cbeta_id": cbeta, "title_zh": title, "juan_num": juan}


DB = FakeDB(
    texts={15: ("T0374", "大般涅槃經")},
    contents={(15, 13): JUAN_13, (15, 16): JUAN_16, (15, 1): JUAN_OTHER},
)


# ── windowing parity ─────────────────────────────────────────────────────


def test_windowed_best_span_never_scores_below_the_chat_path():
    """The public scan adds anchor-derived window starts the chat-path scan
    never tries, so it can only find an equal or better window — never a worse
    one. quote_verifier is deliberately not changed: its numbers are the
    baseline the faithfulness metrics are tracked against."""
    needle = normalise_for_match(SNOW_VERSE)
    for haystack_raw in (JUAN_13, JUAN_16, JUAN_OTHER, SNOW_VERSE, "短"):
        haystack = normalise_for_match(haystack_raw)
        ratio, start, end = windowed_best_span(needle, haystack)
        assert ratio >= _windowed_ratio(needle, haystack) - 1e-9
        assert ratio <= 1.0
        assert 0 <= start <= end <= len(haystack)


def test_anchoring_frames_the_window_on_the_match():
    """A long fascicle scanned coarsely lands the window *near* the match; the
    anchor pass has to land it *on* the match, or the diff is unreadable."""
    needle = normalise_for_match(SNOW_VERSE)
    haystack = normalise_for_match("如是我聞" * 400 + SNOW_VERSE + "爾時世尊" * 400)
    ratio, start, end = windowed_best_span(needle, haystack)
    assert ratio == pytest.approx(1.0)
    assert haystack[start:end] == needle


def test_diff_ops_name_the_actual_substitution():
    quote = normalise_for_match("諸行無常，是生滅法，生滅滅已，寂滅最樂")
    source = normalise_for_match(SNOW_VERSE)
    ops = diff_ops(quote, source)
    assert [o.op for o in ops if o.op != "equal"], "a changed character must show up"
    replaced = [(o.quote, o.source) for o in ops if o.op == "replace"]
    assert ("最", "为") in replaced          # 最 ← 為, both normalised to 简
    assert "".join(o.quote for o in ops) == quote
    assert "".join(o.source for o in ops) == source


def test_diff_ops_empty_when_either_side_missing():
    assert diff_ops("", "abc") == []
    assert diff_ops("abc", "") == []


# ── service verdicts ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exact_hit_with_cite_and_juan():
    out = await verify_quote(DB, FakeES(), SNOW_VERSE, cite="T0374", juan=13)
    assert out.verbatim is True
    assert out.bucket == "exact"
    assert out.similarity == 1.0
    assert out.cite_resolved is True
    assert out.cite_matched is True
    m = out.matches[0]
    assert (m.text_id, m.juan_num, m.juan_matched) == (15, 13, True)
    assert m.urn == "fojin:cbeta/T0374.13"


@pytest.mark.asyncio
async def test_wrong_juan_hint_is_honest():
    """Quote真身在卷13/16，提示卷1：verbatim 仍为 True（开放世界事实），
    但 cite_matched 必须是 False，命中行标 juan_matched=False。"""
    es = FakeES({"match_phrase": [_hit(15, 13), _hit(15, 16)]})
    out = await verify_quote(DB, es, SNOW_VERSE, cite="T0374", juan=1)
    assert out.verbatim is True
    assert out.cite_matched is False
    assert all(m.juan_matched is False for m in out.matches)
    assert {m.juan_num for m in out.matches} == {13, 16}


@pytest.mark.asyncio
async def test_open_world_no_cite():
    es = FakeES({"match_phrase": [_hit(15, 13)]})
    out = await verify_quote(DB, es, SNOW_VERSE)
    assert out.verbatim is True
    assert out.cite_resolved is None and out.cite_matched is None
    assert out.matches[0].juan_matched is None


@pytest.mark.asyncio
async def test_near_miss_reports_closest_window():
    corrupted = "諸行無常，是生滅法，生滅滅已，寂滅最樂也"  # 為→最 + 也
    es = FakeES({"match_phrase": [], "match": [_hit(15, 13)]})
    out = await verify_quote(DB, es, corrupted)
    assert out.verbatim is False
    assert out.bucket == "near_miss"
    assert out.similarity >= 0.85
    assert out.closest is not None
    assert out.closest.urn == "fojin:cbeta/T0374.13"
    assert "生灭灭已" in out.closest.window_normalised  # normalised (simplified) space
    # "差异在哪": the verdict must name the changed characters, not merely
    # score the miss.
    changed = [(o.op, o.quote, o.source) for o in out.closest.diff if o.op != "equal"]
    assert changed, "a near miss must come with the differences spelled out"
    assert "".join(o.quote for o in out.closest.diff) == out.normalised_quote
    assert "".join(o.source for o in out.closest.diff) == out.closest.window_normalised


@pytest.mark.asyncio
async def test_absent_when_nothing_close():
    es = FakeES({"match_phrase": [], "match": [_hit(15, 1)]})
    out = await verify_quote(DB, es, "此句純屬虛構絕不在藏經之中者也")
    assert out.verbatim is False
    assert out.bucket == "absent"


@pytest.mark.asyncio
async def test_unresolvable_cite_still_searches_open_world():
    es = FakeES({"match_phrase": [_hit(15, 13)]})
    out = await verify_quote(DB, es, SNOW_VERSE, cite="T9999")
    assert out.cite_resolved is False
    assert out.cite_matched is False
    assert out.verbatim is True  # found anyway — the useful answer


@pytest.mark.asyncio
async def test_urn_cite_hint_carries_juan():
    out = await verify_quote(DB, FakeES(), SNOW_VERSE, cite="fojin:cbeta/T0374.13")
    assert out.cite_resolved is True
    assert out.cite_matched is True
    assert out.matches[0].juan_matched is True


@pytest.mark.asyncio
async def test_too_short_quote_rejected():
    """Below one 四字句 there is nothing to answer either way."""
    with pytest.raises(QuoteTooShortError):
        await verify_quote(DB, FakeES(), "諸行無")


@pytest.mark.asyncio
async def test_four_character_quote_is_answered_not_refused():
    """色即是空 / 應無所住而生其心 are the phrases people most need checked;
    the old 12-character floor refused exactly those."""
    es = FakeES({"match_phrase": [_hit(15, 13)]})
    out = await verify_quote(DB, es, "諸行無常")
    assert out.verbatim is True
    assert out.matches[0].urn == "fojin:cbeta/T0374.13"


@pytest.mark.asyncio
async def test_short_quote_says_what_its_verdict_is_worth():
    """A four-character hit is nearly always true and nearly always
    uninformative — the verdict has to say so rather than let the caller
    read it as provenance."""
    es = FakeES({"match_phrase": [_hit(15, 13)]})
    short = await verify_quote(DB, es, "諸行無常")
    long = await verify_quote(DB, es, SNOW_VERSE)
    assert any("short" in c.lower() for c in short.caveats)
    assert not any("short" in c.lower() for c in long.caveats)


@pytest.mark.asyncio
async def test_capped_match_list_is_flagged():
    """Five matches is the cap, not a census — saying so is the difference
    between a sample and a false claim of completeness."""
    es = FakeES({"match_phrase": [_hit(15, j) for j in (13, 16)]})
    out = await verify_quote(DB, es, SNOW_VERSE)
    assert out.matches_capped is False        # two hits, cap is five

    from app.services import quote_lookup

    wide = FakeDB(
        texts={15: ("T0374", "大般涅槃經")},
        contents={(15, j): JUAN_13 for j in range(1, 9)},
    )
    es_wide = FakeES({"match_phrase": [_hit(15, j) for j in range(1, 9)]})
    out2 = await verify_quote(wide, es_wide, SNOW_VERSE)
    assert len(out2.matches) == quote_lookup._MAX_CANDIDATES
    assert out2.matches_capped is True


@pytest.mark.asyncio
async def test_matches_carry_a_clickable_absolute_url():
    """A relative path is unusable to an agent with no host: in a real
    session it linked CBETA instead, and fojin's verification went
    uncredited."""
    out = await verify_quote(DB, FakeES(), SNOW_VERSE, cite="T0374", juan=13)
    url = out.matches[0].reader_url
    assert url is not None and url.startswith("https://")
    assert url.endswith("/reader?text=15&juan=13")


# ── rate limit registration ──────────────────────────────────────────────


def test_verify_quote_is_strict_rate_limited():
    assert STRICT_PATHS["/api/verify/quote"] == settings.rate_limit_verify_quote
    assert settings.rate_limit_verify_quote <= settings.rate_limit_default
