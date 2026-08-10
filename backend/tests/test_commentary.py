"""经注对读服务。

数据包不随仓库发布，所以这里用合成包测行为，另外专门守住「没有包时会怎样」——
线上少一个功能好过整个后端起不来。
"""

import json
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
