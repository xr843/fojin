"""经注对读服务。

数据包不随仓库发布，所以这里用合成包测行为，另外专门守住「没有包时会怎样」——
线上少一个功能好过整个后端起不来。
"""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

if "elasticsearch" not in sys.modules:
    _es = MagicMock()
    _es.AsyncElasticsearch = MagicMock
    sys.modules["elasticsearch"] = _es

from app.services import commentary as svc

# 繁体原文，逐行拆开——CBETA 一行才十来个字，所以查询必然跨行。
LINES = [
    {"id": "T08n0235_p0749c19", "text": "薩莊嚴佛土不？」「不也，世尊！"},
    {"id": "T08n0235_p0749c20", "text": "是故須菩提，諸菩薩摩訶薩應如是生清淨心，"},
    {"id": "T08n0235_p0749c21", "text": "不應住色生心，不應住聲、香、味、"},
    {"id": "T08n0235_p0749c22", "text": "觸、法生心，應無所住而生其心。"},
    {"id": "T08n0235_p0749c23", "text": "「須菩提！譬如有人，身如須彌山王，"},
]


def _pkg(tmp_path, notes):
    data = {
        "meta": {
            "schema": 1, "base_work": "T08n0235", "base_title": "金剛般若波羅蜜經",
            "commentary_count": 3, "note_count": len(notes), "line_count": len(LINES),
            "lines_with_notes": 3, "passage_radius": 3,
        },
        "base_lines": LINES,
        "commentaries": {
            "F03n0100": {"title": "御注並序", "tier": "A", "same_as": None},
            "ZW10n0081": {"title": "御注金剛般若經", "tier": "A", "same_as": "F03n0100"},
            "X24n0461": {"title": "金剛經註", "tier": "C", "same_as": None},
        },
        "notes": notes,
    }
    d = tmp_path / "commentary"
    d.mkdir(exist_ok=True)
    (d / "diamond.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d


def _passage(pkg, quote, limit):
    """读者划一段 → 各家注。locate 决定他划到了哪几行，passage 据此排序。"""
    loc = pkg.locate(quote)
    assert loc is not None, f"划选未命中: {quote}"
    core, i0, i1 = loc
    return pkg.passage(core, i0, i1, limit)


def _note(work, base_line, anchor, score, text):
    return {"work": work, "base_line": base_line, "anchor": anchor,
            "score": score, "text": text}


@pytest.fixture()
def loaded(tmp_path, monkeypatch):
    notes = [
        _note("F03n0100", "T08n0235_p0749c21", "F03n0100_p0334b10", 1.0, "知色相空"),
        # 同一部书在段内第二处锚点，置信更低——去重后应只留上面那条
        _note("F03n0100", "T08n0235_p0749c22", "F03n0100_p0334b14", 0.8, "重复锚点"),
        _note("ZW10n0081", "T08n0235_p0749c21", "ZW10n0081_p0073a07", 1.0, "另一版本"),
        _note("X24n0461", "T08n0235_p0749c22", "X24n0461_p0546b12", 1.0, "此修行人"),
    ]
    d = _pkg(tmp_path, notes)
    monkeypatch.setattr(svc, "PACKAGE_DIR", d)
    svc.packages.cache_clear()
    yield
    svc.packages.cache_clear()


def test_missing_package_dir_is_not_an_error(tmp_path, monkeypatch):
    """没装数据包时必须静默降级——后端不能因为少一份可选数据起不来。"""
    monkeypatch.setattr(svc, "PACKAGE_DIR", tmp_path / "nope")
    svc.packages.cache_clear()
    assert svc.packages() == []
    assert svc.available() == []
    svc.packages.cache_clear()


def test_corrupt_package_is_skipped_not_raised(tmp_path, monkeypatch):
    d = tmp_path / "commentary"
    d.mkdir()
    (d / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(svc, "PACKAGE_DIR", d)
    svc.packages.cache_clear()
    assert svc.packages() == []
    svc.packages.cache_clear()


def test_finds_a_quote_that_spans_lines(loaded):
    """CBETA 一行十来个字，任何完整句子都跨行；逐行匹配一定找不到。"""
    pkg = svc.packages()[0]
    assert pkg.find("應無所住而生其心") == "T08n0235_p0749c22"


def test_simplified_query_matches_traditional_source(loaded):
    """读者按简体输入，语料是繁体。归一化用的是 quote_verifier 那一份，
    全站「同一句经文」只能有一个定义。"""
    pkg = svc.packages()[0]
    assert pkg.find("应无所住而生其心") == "T08n0235_p0749c22"


def test_passage_merges_neighbouring_lines(loaded):
    """注家把牒文锚在同一段的不同行上；只看锚点那一行会把一段的注切碎。"""
    pkg = svc.packages()[0]
    span, hits, total = _passage(pkg, "不應住色生心，不應住聲、香、味、觸、法生心，應無所住而生其心。", 10)
    assert len(span) >= 4
    # c21 上的两家 + c22 上的一家，跨行合并后都在
    assert {h["work"] for h in hits} == {"F03n0100", "ZW10n0081", "X24n0461"}
    assert total == 3


def test_one_entry_per_commentary_keeping_best_anchor(loaded):
    """同一部书段内多处锚点只算一家，否则「有几家注」会被答成「有几条对齐」。"""
    pkg = svc.packages()[0]
    _, hits, _ = _passage(pkg, "不應住色生心，不應住聲、香、味、觸、法生心，應無所住而生其心。", 10)
    f = [h for h in hits if h["work"] == "F03n0100"]
    assert len(f) == 1
    assert f[0]["score"] == 1.0            # 留置信度高的那个锚点
    assert f[0]["text"] == "知色相空"


def test_limit_reports_the_true_total(loaded):
    """截断时必须能看出被截断了——列出三家不能让人以为只有三家。"""
    pkg = svc.packages()[0]
    _, hits, total = _passage(pkg, "不應住色生心，不應住聲、香、味、觸、法生心，應無所住而生其心。", 2)
    assert len(hits) == 2
    assert total == 3


def test_tier_orders_before_score(loaded):
    """A 档在前：质检档次比单条置信度更能说明这部书可不可信。

    档次只在「读者划到的那几行」内部比 —— 所以这里划的是 c21+c22 两行，
    三家注都落在划选内。跨越划选边界时另有更强的次序，见下面那条测试。
    """
    pkg = svc.packages()[0]
    _, hits, _ = _passage(pkg, "不應住色生心，不應住聲、香、味、觸、法生心，應無所住而生其心。", 10)
    assert hits[-1]["work"] == "X24n0461"   # 唯一的 C 档排最后


def test_unknown_quote_returns_nothing_rather_than_guessing(loaded):
    pkg = svc.packages()[0]
    assert pkg.find("此句不在本经之中") is None


@pytest.mark.parametrize(
    "work,expected",
    [("T08n0235", "T0235"), ("X24n0461", "X0461"), ("ZW10n0081", "ZW0081"),
     ("F03n0100", "F0100"), ("garbage", None)],
)
def test_cbeta_id_conversion(work, expected):
    assert svc.to_cbeta_id(work) == expected


@pytest.mark.parametrize(
    "anchor,expected",
    [
        ("X24n0456_p0455c03", "0455c03"),
        ("T08n0235_p0749c19", "0749c19"),
        ("ZW10n0081_p0123a01", "0123a01"),
        # 行标缺失或不成形——退回书级，别拼一个跳不到的锚点。
        (None, None),
        ("", None),
        ("T08n0235", None),
        ("T08n0235_p", None),
    ],
)
def test_line_ref_extraction(anchor, expected):
    assert svc.line_ref(anchor) == expected


# --- 链接落到行 -------------------------------------------------------------
#
# 真实数据上的形状已经用生产库验过（见 api/commentary 里 _JUAN_OF_LINE 的注释）：
# 大正藏精确命中，卍续藏落在同页邻行，跨卷的 0467a11 正确解到第 3 卷。下面守的
# 是把查询结果拼成链接这一段，以及三档退化各自退到哪。


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _FakeDB:
    """按调用顺序吐预设结果：第一次是书号→text_id，第二次是行标→卷。"""

    def __init__(self, *results):
        self._results = list(results)

    async def execute(self, _stmt, _params=None):
        return _Rows(self._results.pop(0) if self._results else [])


@pytest.mark.asyncio
async def test_link_lands_on_the_line_when_the_anchor_resolves():
    from app.api.commentary import _locate

    db = _FakeDB([("X0456", 12400)], [(12400, "0455c03", 1, "0455c02")])
    got = await _locate(db, [("X24n0456", "X24n0456_p0455c03")])
    urn, url = got[("X24n0456", "X24n0456_p0455c03")]
    # 滚动落点是索引里真有的那一行，不是 anchor 本身——指向页面上不存在的行，
    # 阅读器什么也不做，看起来就像链接坏了。
    assert url == "https://fojin.app/texts/12400/read?juan=1&anchor=p0455c02"
    assert urn == "fojin:cbeta/X0456.1#p0455c02"


@pytest.mark.asyncio
async def test_falls_back_to_the_book_when_the_page_has_no_indexed_line():
    from app.api.commentary import _locate

    db = _FakeDB([("X0456", 12400)], [])  # 同页一行都没索引到
    got = await _locate(db, [("X24n0456", "X24n0456_p0455c03")])
    urn, url = got[("X24n0456", "X24n0456_p0455c03")]
    assert url == "https://fojin.app/texts/12400"
    assert urn == "fojin:cbeta/X0456"


@pytest.mark.asyncio
async def test_no_link_at_all_when_the_work_is_not_in_the_corpus():
    from app.api.commentary import _locate

    # 注疏多收在藏外丛书里，未必都在语料内。宁可不给，也不给点不开的。
    db = _FakeDB([], [])
    got = await _locate(db, [("B07n0023", "B07n0023_p0123a01")])
    assert got[("B07n0023", "B07n0023_p0123a01")] == ("fojin:cbeta/B0023", None)


@pytest.mark.asyncio
async def test_one_round_trip_regardless_of_how_many_commentaries():
    from app.api import commentary as api

    calls = []

    class _Counting(_FakeDB):
        async def execute(self, stmt, params=None):
            calls.append(params)
            return await super().execute(stmt, params)

    db = _Counting(
        [("X0456", 12400), ("X0461", 12403)],
        [(12400, "0455c03", 1, "0455c02"), (12403, "0455c03", 2, "0455c01")],
    )
    await api._locate(db, [
        ("X24n0456", "X24n0456_p0455c03"),
        ("X24n0461", "X24n0461_p0455c03"),
    ])
    # 两次查库，与注家数量无关——一段常有 50 家，逐条查会打爆数据库。
    assert len(calls) == 2


# 上面几个用的是 DB 替身，守的是「查询结果怎么拼成链接」。_JUAN_OF_LINE 这条
# SQL 本身它们一行也没执行过——去掉同页约束，它们照样全绿（试过）。而这条查询
# 用了 unnest / DISTINCT ON / left()，都是 Postgres 专有的，换不成 SQLite。
#
# 所以真正守它的是下面这个：给了真库就跑，没给就明确跳过，不拿一个从没执行过
# 的查询冒充「已覆盖」。案例是 2026-08-12 在生产库上验过的那批。
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("FOJIN_TEST_DATABASE_URL"),
    reason="需要 FOJIN_TEST_DATABASE_URL 指向一个装了 CBETA 语料的库",
)
async def test_juan_lookup_against_a_real_corpus():
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.api.commentary import _JUAN_OF_LINE

    cases = [
        # (text_id, 目标行标, 期望卷, 期望落点)
        (7, "0749c19", 1, "0749c19"),      # 经文侧：大正藏，精确命中
        (7872, "0096c20", 2, "0096c20"),   # 注疏侧：大正藏，精确命中
        (12400, "0448c02", 1, "0448c01"),  # 卍续藏：同页邻行，差一行
        (12400, "0455c03", 1, "0455c02"),
        (12400, "0467a11", 3, "0467a10"),  # 跨卷：同页约束把它正确解到第 3 卷
    ]
    engine = create_async_engine(os.environ["FOJIN_TEST_DATABASE_URL"])
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(_JUAN_OF_LINE, {
                "tids": [c[0] for c in cases],
                "refs": [c[1] for c in cases],
            })).all()
    finally:
        await engine.dispose()

    got = {(t, r): (j, n) for t, r, j, n in rows}
    for tid, ref, juan, near in cases:
        assert got.get((tid, ref)) == (juan, near), f"{tid}/{ref}"

    # 行标不成形时一行都不该返回——调用方据此退回书级。
    rows = []
    async with create_async_engine(os.environ["FOJIN_TEST_DATABASE_URL"]).connect() as conn:
        rows = (await conn.execute(
            _JUAN_OF_LINE, {"tids": [12400], "refs": ["9999z99"]}
        )).all()
    assert rows == []


def test_locate_covers_the_whole_selection_not_just_its_start(loaded):
    """划选跨几行就该收几行 —— 只认起点会把读者没划的上文也当成正题。"""
    pkg = svc.packages()[0]
    core, i0, i1 = pkg.locate(
        "不應住色生心，不應住聲、香、味、觸、法生心，應無所住而生其心。"
    )
    assert core == {"T08n0235_p0749c21", "T08n0235_p0749c22"}
    assert pkg.ids[i0] == "T08n0235_p0749c21"
    assert pkg.ids[i1] == "T08n0235_p0749c22"


def test_boundary_line_grazed_by_a_few_chars_is_not_core(loaded):
    """读者几乎不会正好停在 CBETA 行末；末尾沾到的那一两个字不算他在问它。

    不设这道门槛的话，下一句的注家会挤满名额 —— 生产 44 例抽样里实测撞到 1 例。
    """
    pkg = svc.packages()[0]
    core, _, _ = pkg.locate("觸、法生心，應無所住而生其心。「須")
    assert "T08n0235_p0749c23" not in core
    assert core == {"T08n0235_p0749c22"}


@pytest.fixture()
def upstream_is_better_graded(tmp_path, monkeypatch):
    """上文两家是 A 档，读者划的那一行只有一家 C 档 —— 次序该听谁的。"""
    notes = [
        _note("F03n0100", "T08n0235_p0749c20", "F03n0100_p0334b01", 1.0, "註上文一"),
        _note("ZW10n0081", "T08n0235_p0749c21", "ZW10n0081_p0073a01", 1.0, "註上文二"),
        _note("X24n0461", "T08n0235_p0749c22", "X24n0461_p0546b12", 1.0, "註本句"),
    ]
    d = _pkg(tmp_path, notes)
    monkeypatch.setattr(svc, "PACKAGE_DIR", d)
    svc.packages.cache_clear()
    yield
    svc.packages.cache_clear()


def test_notes_on_the_selected_line_outrank_upstream_ones(upstream_is_better_graded):
    """读者划哪句，就先给注那句的 —— 哪怕它档次更低。

    这是这个功能此前最大的毛病：窗口向前多放三行，而上文的注按档次/置信度
    排在前面，于是读者划 A 段、看到的是 B 段的注。生产 44 例抽样里，注文与
    划选对得上的只有 27%，其中 15 例八家全部答非所问。
    """
    pkg = svc.packages()[0]
    _, hits, _ = _passage(pkg, "應無所住而生其心", 10)
    # X24n0461 是 C 档，另外两家是 A 档；但只有它注的是读者划的这一行。
    assert hits[0]["work"] == "X24n0461"
    assert hits[0]["base_line"] == "T08n0235_p0749c22"
    # 上文那两家仍然给，但退到后面当兜底 —— 对齐锚点有偏移，全砍掉会有段取不到注。
    assert {h["work"] for h in hits[1:]} == {"F03n0100", "ZW10n0081"}


def test_a_books_anchor_on_the_selected_line_beats_its_own_higher_scored_one(loaded):
    """一部书在段内多处有锚点时，给读者看它注**这一句**的那条。

    F03n0100 在 c21 的锚点置信度更高（1.0 vs 0.8），但读者划的是 c22；
    注 c21 的那条再准，也不是他问的问题。
    """
    pkg = svc.packages()[0]
    _, hits, _ = _passage(pkg, "應無所住而生其心", 10)
    f = [h for h in hits if h["work"] == "F03n0100"]
    assert len(f) == 1
    assert f[0]["base_line"] == "T08n0235_p0749c22"
    assert f[0]["score"] == 0.8


# ---------------------------------------------------------------- 反查
#
# 正查（经文 → 各家注）回答不了读注疏的人真正的问题。90 天 Umami 实测：被点开
# 的引文里注疏 93 次、论本文 28 次 —— 他们在读注疏，而读注疏最难的是不知道眼前
# 这段在解释哪一句论。索引方向是反的，数据本身双向都有（每条对齐两端都带行号）。


@pytest.fixture()
def reverse_loaded(tmp_path, monkeypatch):
    notes = [
        _note("F03n0100", "T08n0235_p0749c20", "F03n0100_p0334b10", 1.0, "牒是故須菩提"),
        _note("F03n0100", "T08n0235_p0749c21", "F03n0100_p0334b14", 0.9, "牒不應住色生心"),
        _note("F03n0100", "T08n0235_p0749c22", "F03n0100_p0334c02", 0.8, "牒應無所住"),
        # 同一部书在同一句论文上的第二处锚点，置信更低 —— 去重后应只留上面那条
        _note("F03n0100", "T08n0235_p0749c22", "F03n0100_p0334c05", 0.5, "同句第二处"),
        _note("X24n0461", "T08n0235_p0749c23", "X24n0461_p0546b12", 1.0, "别的书"),
    ]
    d = _pkg(tmp_path, notes)
    monkeypatch.setattr(svc, "PACKAGE_DIR", d)
    svc.packages.cache_clear()
    yield
    svc.packages.cache_clear()


def test_reverse_maps_a_run_of_commentary_lines_to_the_base_lines_it_quotes(reverse_loaded):
    pkg = svc.packages()[0]
    hits = pkg.source("F03n0100", "0334b10", "0334b14", 8)
    assert [h["base_line"] for h in hits] == [
        "T08n0235_p0749c20",
        "T08n0235_p0749c21",
    ]


def test_reverse_excludes_anchors_outside_the_cited_lines(reverse_loaded):
    """读者看的是注疏的这一块，不是整部书 —— 区间外的锚点不能算。"""
    pkg = svc.packages()[0]
    hits = pkg.source("F03n0100", "0334b14", "0334b99", 8)
    assert [h["base_line"] for h in hits] == ["T08n0235_p0749c21"]


def test_reverse_keeps_the_best_anchor_per_base_line(reverse_loaded):
    """一部注疏常在同一句论文上牒好几处；按论文句去重，留最贴的那处。"""
    pkg = svc.packages()[0]
    hits = pkg.source("F03n0100", "0334c01", "0334c09", 8)
    assert len(hits) == 1
    assert hits[0]["score"] == 0.8


def test_reverse_never_mixes_in_another_book(reverse_loaded):
    pkg = svc.packages()[0]
    hits = pkg.source("F03n0100", "0000a01", "9999z99", 8)
    assert {h["work"] for h in hits} == {"F03n0100"}


def test_reverse_returns_base_lines_in_reading_order(reverse_loaded):
    """按论文的行序给，不按置信度 —— 读者要的是「这块注依次讲了哪几句」。"""
    pkg = svc.packages()[0]
    hits = pkg.source("F03n0100", "0000a01", "9999z99", 8)
    order = [pkg.pos[h["base_line"]] for h in hits]
    assert order == sorted(order)


def test_find_commentary_resolves_a_fojin_book_id(reverse_loaded):
    """抽屉手里只有 fojin 的书号（F0100），包里写的是 CBETA 全号（F03n0100）。"""
    assert svc.find_commentary("F0100") == [(svc.packages()[0], "F03n0100")]
    assert svc.find_commentary("T0001") == []


# ------------------------------------------------- 反查端点：字符位置 → 行标


def _anchors(*pairs):
    return [{"char_offset": o, "line_ref": r} for o, r in pairs]


def test_span_lines_starts_at_the_line_the_quote_begins_in():
    """锚点标的是一行的起点，落在行中间的字属于上一行。"""
    from app.api.commentary import _span_lines

    a = _anchors((0, "0460b04"), (17, "0460b05"), (34, "0460b06"))
    assert _span_lines(a, 20, 30) == ("0460b05", "0460b05")


def test_span_lines_covers_every_line_the_quote_touches():
    from app.api.commentary import _span_lines

    a = _anchors((0, "0460b04"), (17, "0460b05"), (34, "0460b06"), (51, "0460b07"))
    assert _span_lines(a, 5, 40) == ("0460b04", "0460b06")


def test_span_lines_falls_back_to_the_first_line_before_any_anchor():
    """卷首 <lb> 之前的那几个字没有锚点——退到首行，不要整次查询作废。"""
    from app.api.commentary import _span_lines

    a = _anchors((10, "0460b04"), (27, "0460b05"))
    assert _span_lines(a, 0, 5) == ("0460b04", "0460b04")


def test_span_lines_gives_up_when_the_juan_has_no_anchors():
    from app.api.commentary import _span_lines

    assert _span_lines([], 0, 10) is None


# ------------------------------------------------- 反查端点：整条链路


class _ReverseResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar(self):
        return self._rows[0][0] if self._rows else None

    def fetchall(self):
        return self._rows

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _ReverseDB:
    """按 SQL 片段作答的假会话。真库不在测试环境里，但这条链路值得整条走一遍：
    参数名、schema、退化分支接错了，单测各自都还是绿的。"""

    def __init__(self, juan_content, chunk, anchors):
        self.juan_content, self.chunk, self.anchors = juan_content, chunk, anchors

    async def execute(self, stmt, params=None):
        s = str(stmt)
        if "FROM buddhist_texts WHERE id" in s:
            return _ReverseResult([("F0100",)])
        if "text_embeddings" in s:
            return _ReverseResult([(self.chunk,)])
        if "text_contents" in s:
            return _ReverseResult([(self.juan_content,)])
        if "text_line_anchors" in s and "unnest" not in s:
            return _ReverseResult([(a["char_offset"], a["line_ref"]) for a in self.anchors])
        if "cbeta_id = ANY" in s:
            return _ReverseResult([("T0235", 7)])
        if "unnest" in s:          # _JUAN_OF_LINE
            return _ReverseResult([(7, "0749c21", 1, "0749c21")])
        raise AssertionError(f"没想到的查询: {s[:60]}")


@pytest_asyncio.fixture
async def source_client(reverse_loaded):
    from fastapi import FastAPI

    from app.api import commentary as api
    from app.database import get_db

    content = "注文甲" * 10 + "注文乙" * 10
    db = _ReverseDB(
        juan_content=content,
        chunk=content[5:35],
        # 注疏自己的行：这块引文横跨 b10–b14，正是 fixture 里两条锚点所在
        anchors=[{"char_offset": o, "line_ref": r} for o, r in
                 ((0, "0334b10"), (15, "0334b12"), (30, "0334b14"), (45, "0334c02"))],
    )

    async def fake_db():
        yield db

    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[get_db] = fake_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_source_endpoint_answers_which_lines_this_commentary_explains(source_client):
    r = await source_client.get("/api/commentary/source?text_id=99&juan=1&chunk_index=0")
    assert r.status_code == 200
    d = r.json()
    assert d["matched"] is True
    assert d["work"] == "F03n0100"
    assert d["base_work"] == "T08n0235"
    # 这块注文牒了两句论 —— 按论文行序给，不按置信度
    assert [p["base_line"] for p in d["passages"]] == [
        "T08n0235_p0749c20",
        "T08n0235_p0749c21",
    ]
    # 被牒那行 ± 1 行，够读成一句话
    assert "不應住色生心" in d["passages"][1]["base_text"]
    assert d["passages"][0]["reader_url"]


@pytest.mark.asyncio
async def test_source_endpoint_says_so_when_the_book_has_no_alignment(source_client, monkeypatch):
    """没有对齐数据 ≠ 这部书没在注任何东西。接口必须把这两件事分开说。"""
    monkeypatch.setattr(svc, "find_commentary", lambda cbeta: [])
    r = await source_client.get("/api/commentary/source?text_id=99&juan=1&chunk_index=0")
    d = r.json()
    assert d["matched"] is False
    assert any("不等于" in c for c in d["caveats"])


@pytest.mark.asyncio
async def test_corpus_carries_fojin_text_ids(source_client):
    """抽屉手里只有 text_id。没有这一列，它只能对每条引文都试一次反查。"""
    r = await source_client.get("/api/commentary/corpus")
    assert r.status_code == 200
    d = r.json()
    assert [c["cbeta_id"] for c in d["commentaries"]] == ["F0100", "X0461"]
    # 假库里只有 T0235 这一部，所以注疏侧查不到 —— 查不到就留 None，不要瞎填
    assert d["sutras"][0]["text_id"] == 7
    assert all(c["text_id"] is None for c in d["commentaries"])


# --- 引文块与正文只差换行位置 -------------------------------------------------


@pytest_asyncio.fixture
async def rewrapped_source_client(reverse_loaded):
    """生产实况：chunk_text 与 text_contents 的 content 出自同一份正文，
    但换行位置不同（CBETA 的硬换行两处存法不一样）。

    2026-09-22 在生产上抽 160 条注疏引文实测：精确子串 ``content.find(quote)``
    对其中 **95%** 返回 -1，端点一路退到「定位不到」—— 也就是说反查对二十分之
    十九的引文是哑的，而且失败是静默的。改成忽略空白定位后覆盖率 5% → 36%。
    """
    from fastapi import FastAPI

    from app.api import commentary as api
    from app.database import get_db

    raw = "注文甲" * 10 + "注文乙" * 10
    # 正文在这两处断行，引文块在另一处断行 —— 两边都是同一段字，只是换行不同。
    content = raw[:12] + "\n" + raw[12:28] + "\n\n" + raw[28:]
    quote_raw = raw[5:35]
    chunk = quote_raw[:7] + "\n" + quote_raw[7:]
    assert chunk not in content, "这个 fixture 必须造出精确匹配找不到的情形"

    db = _ReverseDB(
        juan_content=content,
        chunk=chunk,
        anchors=[{"char_offset": o, "line_ref": r} for o, r in
                 ((0, "0334b10"), (15, "0334b12"), (30, "0334b14"), (45, "0334c02"))],
    )

    async def fake_db():
        yield db

    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[get_db] = fake_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_source_locates_a_chunk_whose_line_breaks_differ_from_the_juan(
    rewrapped_source_client,
):
    r = await rewrapped_source_client.get(
        "/api/commentary/source?text_id=99&juan=1&chunk_index=0"
    )
    assert r.status_code == 200
    d = r.json()
    assert d["matched"] is True, d["caveats"]
    assert d["passages"], "换行位置不同不该让反查退化成空结果"
