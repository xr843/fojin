"""贴原文定位：每一个决策点一条用例。上线门见 eval/paste_locate/GATE.md。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import passage_locator as pl
from app.services.quote_verifier import normalise_for_match

norm = pl.fast_normalise

SUTRA = "佛告須菩提：凡所有相，皆是虛妄。若見諸相非相，則見如來。須菩提白佛言"
COMMENTARY = "經云：凡所有相，皆是虛妄。若見諸相非相，則見如來。此明離相見佛之義也。"


def _chunk(cbeta_id: str, text: str, *, text_id: int = 1, juan: int = 1, idx: int = 0) -> dict:
    return {
        "text_id": text_id, "juan_num": juan, "chunk_index": idx, "chunk_text": text,
        "score": 1.0, "title_zh": cbeta_id, "lang": "lzh", "source_id": 1, "cbeta_id": cbeta_id,
    }


# ── 切句与窗口 ──────────────────────────────────────────────────────────


def test_split_clauses_drops_single_char_fragments():
    assert pl.split_clauses("佛言：善哉！須菩提，汝今諦聽。") == ["佛言", "善哉", "須菩提", "汝今諦聽"]
    assert pl.split_clauses("嗯，好") == []


def test_best_window_ignores_the_modern_question_around_the_passage():
    msg = "请解释一下：凡所有相，皆是虚妄。若见诸相非相，则见如来。这句话是什么意思？"
    clauses = pl.split_clauses(msg)
    w = pl.best_window([norm(c) for c in clauses], norm(SUTRA))
    assert w is not None
    assert w.text(clauses) == "凡所有相，皆是虚妄，若见诸相非相，则见如来"
    assert w.han == 18


def test_best_window_requires_clauses_to_be_adjacent_in_the_source():
    # 两句各自都在原文里，但原文中并不相邻——不能拼成一个窗口
    clauses = ["佛告須菩提", "則見如來"]
    w = pl.best_window([norm(c) for c in clauses], norm(SUTRA))
    assert w is not None and w.end - w.start == 1


# ── 选出处 ───────────────────────────────────────────────────────────────


def test_canon_rank_key_orders_sutra_before_treatise_before_commentary():
    ids = ["X0506", "T1509", "J0001", "T0235", "T1822"]
    assert sorted(ids, key=pl.canon_rank_key) == ["T0235", "T1509", "T1822", "J0001", "X0506"]


def test_pick_prefers_the_root_sutra_when_a_commentary_quotes_the_same_passage():
    clauses = pl.split_clauses("凡所有相，皆是虚妄。若见诸相非相，则见如来。")
    picked = pl.pick_located(clauses, [_chunk("X0506", COMMENTARY, text_id=9), _chunk("T0235", SUTRA, text_id=7)])
    assert picked is not None and picked[0]["cbeta_id"] == "T0235"


def test_pick_prefers_the_longer_window_over_canon_order():
    # 用户贴的是注文本身（含注者自己的话），只有注疏里有完整的窗口
    clauses = pl.split_clauses("凡所有相，皆是虚妄。若见诸相非相，则见如来。此明离相见佛之义也。")
    picked = pl.pick_located(clauses, [_chunk("T0235", SUTRA, text_id=7), _chunk("X0506", COMMENTARY, text_id=9)])
    assert picked is not None and picked[0]["cbeta_id"] == "X0506"


def test_pick_returns_none_below_the_minimum_window():
    clauses = pl.split_clauses("凡所有相，是什么意思")  # 原文只有 4 个汉字
    assert pl.pick_located(clauses, [_chunk("T0235", SUTRA)]) is None


# ── 注入 ─────────────────────────────────────────────────────────────────


def test_inject_puts_located_first_replaces_same_fascicle_and_caps():
    located = _chunk("T0235", SUTRA, text_id=7, juan=1, idx=3)
    others = [
        _chunk("X0506", COMMENTARY, text_id=9),
        _chunk("T0235", "同卷另一块", text_id=7, juan=1, idx=10),
        *[_chunk(f"T{i:04d}", "x", text_id=100 + i) for i in range(5)],
    ]
    out = pl.inject_located(located, others, 5)
    assert out[0] is located
    assert len(out) == 5
    assert sum(1 for r in out if (r["text_id"], r["juan_num"]) == (7, 1)) == 1


# ── 端到端（假 ES / 假库）────────────────────────────────────────────────


def _fake_es(n_texts: int) -> MagicMock:
    es = MagicMock()
    es.search = AsyncMock(side_effect=lambda index, body, timeout: (
        {"aggregations": {"texts": {"value": n_texts}}} if body.get("size") == 0
        else {"hits": {"hits": [{"_source": {"text_id": 7, "juan_num": 1}}, {"_source": {"text_id": 9, "juan_num": 1}}]}}
    ))
    return es


@pytest.mark.anyio
async def test_locate_end_to_end_picks_root_and_reports_window():
    chunks = [_chunk("X0506", COMMENTARY, text_id=9), _chunk("T0235", SUTRA, text_id=7)]
    with patch.object(pl, "_fetch_chunks", AsyncMock(return_value=chunks)):
        got = await pl.locate_pasted_passage(_fake_es(2), MagicMock(), "凡所有相，皆是虚妄。若见诸相非相，则见如来。何义？")
    assert got is not None
    assert got.chunk["cbeta_id"] == "T0235"
    assert got.window_han == 18 and got.texts_with_window == 2


@pytest.mark.anyio
async def test_locate_skips_stock_formulas_found_in_too_many_texts():
    chunks = [_chunk("T0235", SUTRA, text_id=7)]
    with patch.object(pl, "_fetch_chunks", AsyncMock(return_value=chunks)):
        got = await pl.locate_pasted_passage(
            _fake_es(pl.AMBIGUOUS_TEXTS + 1), MagicMock(), "凡所有相，皆是虚妄。若见诸相非相，则见如来。"
        )
    assert got is None


@pytest.mark.anyio
async def test_locate_short_message_never_queries_es():
    es = _fake_es(1)
    got = await pl.locate_pasted_passage(es, MagicMock(), "什么是般若？")
    assert got is None
    es.search.assert_not_called()


# ── 归一化与原文标点还原 ─────────────────────────────────────────────────


@pytest.mark.parametrize("s", [SUTRA, COMMENTARY, "說一切有部，阿毘達磨大毘婆沙論卷第一", "ＡＢＣ１２３，般若。"])
def test_fast_normalise_matches_the_verifier_normaliser(s):
    assert pl.fast_normalise(s) == normalise_for_match(s)


def test_raw_span_recovers_the_source_punctuation():
    # 用户写「皆是虚妄若见诸相非相」（无逗号），原文在中间有句号
    needle = pl.fast_normalise("皆是虚妄若见诸相非相")
    assert pl.raw_span(SUTRA, needle) == "皆是虛妄。若見諸相非相"
    assert pl.raw_span(SUTRA, pl.fast_normalise("不在原文里的句子")) is None


@pytest.mark.anyio
async def test_count_uses_source_clause_boundaries_not_the_users():
    es = _fake_es(3)
    chunks = [_chunk("T0235", SUTRA, text_id=7)]
    with patch.object(pl, "_fetch_chunks", AsyncMock(return_value=chunks)):
        # 用户的标点与原文不同：「凡所有相皆是虚妄，若见诸相非相则见如来」
        got = await pl.locate_pasted_passage(es, MagicMock(), "凡所有相皆是虚妄，若见诸相非相则见如来")
    assert got is not None and got.texts_with_window == 3
    count_body = next(c.kwargs["body"] for c in es.search.call_args_list if c.kwargs["body"].get("size") == 0)
    phrases = [m["match_phrase"]["content"]["query"] for m in count_body["query"]["bool"]["must"]]
    assert phrases == ["凡所有相", "皆是虛妄", "若見諸相非相", "則見如來"]


# ── 引号不是过滤条件：经里佛说的话就在「」里 ──────────────────────────


def test_sutra_dialogue_inside_corner_quotes_is_still_located():
    dialogue = "佛告須菩提：「凡所有相，皆是虛妄。若見諸相非相，則見如來。」須菩提白佛言"
    clauses = pl.split_clauses("凡所有相，皆是虚妄。若见诸相非相，则见如来。何义？")
    picked = pl.pick_located(clauses, [_chunk("T0235", dialogue, text_id=7)])
    assert picked is not None and picked[0]["cbeta_id"] == "T0235"


def test_named_text_wins_a_tie():
    a = _chunk("T1736", "若有生心，生心是妄，故說不生。佛尚不有，何有無生", text_id=1)
    b = _chunk("X0245", "若有生心，生心是妄，故說不生。佛尚不有，何有無生", text_id=2)
    clauses = pl.split_clauses("若有生心，生心是妄，故说不生。佛尚不有，何有无生？")
    assert pl.pick_located(clauses, [a, b])[0]["text_id"] == 1  # 默认按经号
    assert pl.pick_located(clauses, [a, b], named_text_ids=frozenset({2}))[0]["text_id"] == 2


def test_text_inside_title_marks_is_not_a_passage():
    assert pl.split_clauses("《药师琉璃光如来本愿功德经》等经典如何阐述身病与心病？") == ["等经典如何阐述身病与心病"]
    assert pl.named_titles("如《思益》云：……《楞伽》云") == ["思益", "楞伽"]
