"""经注对读服务。

数据包不随仓库发布，所以这里用合成包测行为，另外专门守住「没有包时会怎样」——
线上少一个功能好过整个后端起不来。
"""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

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
    span, hits, total = pkg.passage("T08n0235_p0749c22", 10)
    assert len(span) >= 4
    # c21 上的两家 + c22 上的一家，跨行合并后都在
    assert {h["work"] for h in hits} == {"F03n0100", "ZW10n0081", "X24n0461"}
    assert total == 3


def test_one_entry_per_commentary_keeping_best_anchor(loaded):
    """同一部书段内多处锚点只算一家，否则「有几家注」会被答成「有几条对齐」。"""
    pkg = svc.packages()[0]
    _, hits, _ = pkg.passage("T08n0235_p0749c22", 10)
    f = [h for h in hits if h["work"] == "F03n0100"]
    assert len(f) == 1
    assert f[0]["score"] == 1.0            # 留置信度高的那个锚点
    assert f[0]["text"] == "知色相空"


def test_limit_reports_the_true_total(loaded):
    """截断时必须能看出被截断了——列出三家不能让人以为只有三家。"""
    pkg = svc.packages()[0]
    _, hits, total = pkg.passage("T08n0235_p0749c22", 2)
    assert len(hits) == 2
    assert total == 3


def test_tier_orders_before_score(loaded):
    """A 档在前：质检档次比单条置信度更能说明这部书可不可信。"""
    pkg = svc.packages()[0]
    _, hits, _ = pkg.passage("T08n0235_p0749c22", 10)
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
