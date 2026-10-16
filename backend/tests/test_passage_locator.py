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


def _hits(*juans: tuple[int, int]) -> list[dict]:
    return [{"_source": {"text_id": t, "juan_num": j}} for t, j in juans]


def _fake_es_full(
    *,
    shortlist: list[tuple[int, int]],
    root_shortlist: list[tuple[int, int]] | None = None,
    all_texts: int,
    root_texts: int,
    carriers: list[tuple[int, int]] = (),
) -> MagicMock:
    """Answers each of the locator's four ES queries:
    通用粗筛 / 经律论粗筛（range 过滤）/ 全藏计数（size 0）/ 经律论逐字载体（collapse）。"""

    def search(index, body, timeout):
        if body.get("size") == 0:
            return {"aggregations": {"texts": {"value": all_texts}}}
        if "collapse" in body:
            return {"hits": {"hits": _hits(*carriers)}, "aggregations": {"texts": {"value": root_texts}}}
        restricted = any("range" in f for f in body["query"]["bool"]["filter"])
        return {"hits": {"hits": _hits(*(root_shortlist if restricted and root_shortlist is not None else shortlist))}}

    es = MagicMock()
    es.search = AsyncMock(side_effect=search)
    return es


def _fake_es(n_texts: int) -> MagicMock:
    return _fake_es_full(shortlist=[(7, 1), (9, 1)], all_texts=n_texts, root_texts=n_texts)


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


# ── 短名单不能被注疏挤满（生产 2026-10-16：《起信論》被定位到《釋摩訶衍論》）──────


QIXIN = "心真如者，即是一法界大總相法門體。所謂心性不生不滅。一切諸法唯依妄念而有差別"
QIXIN_ROOT = "所言義者，則有三種。云何為三？一者體大……" + QIXIN + "，若離心念則無一切境界之相。"
QIXIN_SHIMOHEYAN = "論曰：" + QIXIN + "。釋曰：此中明心真如門。"
QIXIN_SHU = "疏：" + QIXIN + "。此舉真如門之體也。"


QIXIN_BY_JUAN = {
    (12675, 1): _chunk("X0759", QIXIN_SHU, text_id=12675),
    (7842, 2): _chunk("T1668", QIXIN_SHIMOHEYAN, text_id=7842, juan=2, idx=10),
    (51, 1): _chunk("T1666", QIXIN_ROOT, text_id=51, idx=4),
}
QIXIN_MSG = "这段怎么理解：心真如者，即是一法界大總相法門體。所謂心性不生不滅。一切諸法唯依妄念而有差別。"
COMMENTARY_JUANS = [(12675, 1), (7842, 2)]  # 注疏反复引用这段，BM25 把它们排满了通用短名单


async def _fetch_qixin(db, juans):
    return [QIXIN_BY_JUAN[j] for j in juans if j in QIXIN_BY_JUAN]


@pytest.mark.anyio
async def test_root_treatise_is_located_even_when_commentaries_fill_the_shortlist():
    # 本论只在「经律论粗筛」里排得上
    es = _fake_es_full(shortlist=COMMENTARY_JUANS, root_shortlist=[(51, 1)], all_texts=16, root_texts=3)
    with patch.object(pl, "_fetch_chunks", AsyncMock(side_effect=_fetch_qixin)):
        got = await pl.locate_pasted_passage(es, MagicMock(), QIXIN_MSG)
    assert got is not None
    assert got.chunk["cbeta_id"] == "T1666"


@pytest.mark.anyio
async def test_root_text_missed_by_both_shortlists_is_found_by_asking_which_root_texts_carry_it():
    # 两个粗筛都没排上本论（长卷吃 BM25 长度归一化的亏）；选出窗口后按经号问「哪些经律论含这段」
    es = _fake_es_full(
        shortlist=COMMENTARY_JUANS, root_shortlist=[(7842, 2)], all_texts=16, root_texts=3, carriers=[(51, 1)]
    )
    with patch.object(pl, "_fetch_chunks", AsyncMock(side_effect=_fetch_qixin)):
        got = await pl.locate_pasted_passage(es, MagicMock(), QIXIN_MSG)
    assert got is not None
    assert got.chunk["cbeta_id"] == "T1666"
    assert got.texts_with_window == 16
    carrier_body = next(c.kwargs["body"] for c in es.search.call_args_list if "collapse" in c.kwargs["body"])
    assert carrier_body["sort"][0] == {"cbeta_id": "asc"}  # 经号最小的先来


@pytest.mark.anyio
async def test_root_carrier_query_is_stripped_to_bare_characters():
    # 生产实测：卍續藏常见的全角「．」在 content.nopunct 里仍会断开二元组链，短语查询静默落空
    es = MagicMock()
    es.search = AsyncMock(return_value={"hits": {"hits": []}, "aggregations": {"texts": {"value": 0}}})
    await pl._root_carriers(es, "若無想．若非有想非無想，我皆令\n入無餘涅槃而滅")
    body = es.search.call_args.kwargs["body"]
    phrase = next(f["match_phrase"]["content.nopunct"]["query"] for f in body["query"]["bool"]["filter"] if "match_phrase" in f)
    assert phrase == "若無想若非有想非無想我皆令入無餘涅槃而滅"


@pytest.mark.anyio
async def test_root_carrier_lookup_failure_keeps_the_shortlist_pick():
    es = _fake_es_full(shortlist=COMMENTARY_JUANS, root_shortlist=[], all_texts=16, root_texts=3)
    original = es.search.side_effect

    def boom(index, body, timeout):
        if "collapse" in body:
            raise RuntimeError("es down")
        return original(index, body, timeout)

    es.search.side_effect = boom
    with patch.object(pl, "_fetch_chunks", AsyncMock(side_effect=_fetch_qixin)):
        got = await pl.locate_pasted_passage(es, MagicMock(), QIXIN_MSG)
    assert got is not None and got.chunk["cbeta_id"] == "T1668"


# ── 套语判定：本经被注疏大量引用 ≠ 套语 ─────────────────────────────────


XINJING = "以無所得故，菩提薩埵依般若波羅蜜多故，心無罣礙；無罣礙故，無有恐怖"


def _fake_es_counts(all_texts: int, root_texts: int) -> MagicMock:
    return _fake_es_full(shortlist=[(7, 1)], all_texts=all_texts, root_texts=root_texts)


@pytest.mark.anyio
async def test_root_sutra_quoted_by_many_commentaries_is_still_located():
    # 生产实测：《心經》這段全藏 51 部含有，經律論裡只有 3 部（心經諸譯）
    chunks = [_chunk("T0251", "觀自在菩薩……" + XINJING, text_id=7)]
    with patch.object(pl, "_fetch_chunks", AsyncMock(return_value=chunks)):
        got = await pl.locate_pasted_passage(_fake_es_counts(51, 3), MagicMock(), XINJING + "。请解释")
    assert got is not None and got.chunk["cbeta_id"] == "T0251"
    assert got.texts_with_window == 51  # 卡片「另见于 N 部」仍报全藏数


@pytest.mark.anyio
async def test_formula_common_across_root_texts_is_still_suppressed():
    chunks = [_chunk("T0001", "如是我聞：一時，佛在舍衛國祇樹給孤獨園，與大比丘眾", text_id=7)]
    with patch.object(pl, "_fetch_chunks", AsyncMock(return_value=chunks)):
        got = await pl.locate_pasted_passage(
            _fake_es_counts(111, 71), MagicMock(), "如是我聞：一時，佛在舍衛國祇樹給孤獨園。何义？"
        )
    assert got is None


@pytest.mark.anyio
async def test_commentary_pick_uses_the_whole_canon_count():
    # 选中的是注疏（非经律论）：仍按全藏数判套语，不因经律论里没有就放行
    chunks = [_chunk("X0759", "疏：" + XINJING, text_id=9)]
    with patch.object(pl, "_fetch_chunks", AsyncMock(return_value=chunks)):
        got = await pl.locate_pasted_passage(_fake_es_counts(51, 0), MagicMock(), XINJING + "。请解释")
    assert got is None
