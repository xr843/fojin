"""「注疏怎么讲这几句」：两个对齐点之间按牒文截取注疏原文。

合成包：论 6 行，注疏 10 行；对齐点只在论第 0 行与第 5 行上（模拟对齐稀疏）。
读者贴第 2–3 行——直接命中为 0，必须靠插值 + 牒引找到讲它的那段。
"""

import json
import sys
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

if "elasticsearch" not in sys.modules:
    _es = MagicMock()
    _es.AsyncElasticsearch = MagicMock
    sys.modules["elasticsearch"] = _es

from app.services import commentary as svc

W = "T41n1821"
BASE = [
    {"id": "T29n1558_p0001a01", "text": "論曰。諸有漏法皆名為苦。"},
    {"id": "T29n1558_p0001a02", "text": "何以故。違聖心故。"},
    {"id": "T29n1558_p0001a03", "text": "同類因者謂相似法與相似法為同類因"},
    {"id": "T29n1558_p0001a04", "text": "謂善五蘊與善五蘊展轉相望為同類因"},
    {"id": "T29n1558_p0001a05", "text": "染污與染污無記與無記五蘊相望應知亦爾"},
    {"id": "T29n1558_p0001a06", "text": "如是已說同類因相。"},
]
COMM = [
    ["0100a01", "論曰至名為苦者，此釋苦義。"],          # 0 ← 對齊點（論第 0 行）
    ["0100a02", "有漏皆苦，聖者所見。"],
    ["0100a03", "何以故者，徵也。違聖心故者，釋也。"],
    ["0100a04", "此下明第五同類因。"],
    ["0100a05", "相似法與相似法為同類因者，謂善與善等。"],  # 4 ← 牒引論第 2 行
    ["0100a06", "善五蘊展轉相望者，善色望善四蘊亦得。"],
    ["0100a07", "染污無記亦爾者，例同前說。"],
    ["0100a08", "已說同類因者，結也。"],                  # 7 ← 對齊點（論第 5 行）
    ["0100a09", "次明相應因。"],
    ["0100a10", "相應因者，心心所法同所依也。"],
]
NOTES = [
    {"base_line": "T29n1558_p0001a01", "work": W, "anchor": f"{W}_p0100a01", "score": 0.9, "text": COMM[0][1]},
    {"base_line": "T29n1558_p0001a06", "work": W, "anchor": f"{W}_p0100a08", "score": 0.9, "text": COMM[7][1]},
]


def _write(tmp_path, comm_lines=True, comm=COMM):
    data = {
        "meta": {"schema": 2, "base_work": "T29n1558", "base_title": "阿毘達磨俱舍論",
                 "commentary_count": 1, "note_count": len(NOTES), "line_count": len(BASE),
                 "lines_with_notes": 2, "passage_radius": 0},
        "base_lines": BASE,
        "commentaries": {W: {"title": "俱舍論記", "tier": "A"}},
        "notes": NOTES,
    }
    if comm_lines:
        data["commentary_lines"] = {W: comm}
    d = tmp_path / "commentary"
    d.mkdir(exist_ok=True)
    (d / "kosa.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d


@pytest.fixture()
def pkg(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "PACKAGE_DIR", _write(tmp_path))
    svc.packages.cache_clear()
    yield svc.packages()[0]
    svc.packages.cache_clear()


def _ex(pkg, quote):
    _core, i0, i1 = pkg.locate(quote)
    return pkg.excerpts(i0, i1)


def test_interpolates_between_sparse_anchors_and_starts_at_the_quote(pkg):
    # 贴的是论第 2–3 行；对齐点只在第 0、5 行，直接命中为 0
    items = _ex(pkg, "相似法與相似法為同類因謂善五蘊")
    assert len(items) == 1
    e = items[0]
    assert e["work"] == W and e["title"] == "俱舍論記"
    # 起点是首个牒到这几句的注文行，而不是前一个对齐点（「論曰至名為苦者」）
    assert e["line_from"] == "0100a05"
    assert e["text"].startswith("相似法與相似法為同類因者")
    assert e["anchor"] == f"{W}_p0100a05"
    # 截到下一个对齐点之前为止，不越界讲到相应因
    assert "相應因" not in e["text"]


def test_no_excerpt_when_the_span_never_quotes_the_passage(tmp_path, monkeypatch):
    # 同样的对齐点，但中间的注文换成讲别处的——对齐稀疏处跨品错位就是这样
    off = [r if i in (0, 7) else [r[0], "此段別明業果，與前不同。"] for i, r in enumerate(COMM)]
    monkeypatch.setattr(svc, "PACKAGE_DIR", _write(tmp_path, comm=off))
    svc.packages.cache_clear()
    try:
        p = svc.packages()[0]
        assert _ex(p, "相似法與相似法為同類因謂善五蘊") == []
    finally:
        svc.packages.cache_clear()


def test_long_commentary_is_cut_at_a_sentence_end(tmp_path, monkeypatch):
    long = [list(r) for r in COMM]
    long[4] = ["0100a05", "相似法與相似法為同類因者，" + "此義甚深，須廣分別。" * 120]
    monkeypatch.setattr(svc, "PACKAGE_DIR", _write(tmp_path, comm=long))
    svc.packages.cache_clear()
    try:
        e = _ex(svc.packages()[0], "相似法與相似法為同類因謂善五蘊")[0]
        assert e["truncated"] is True
        assert e["text"].endswith("。")
        assert len(e["text"]) <= svc.EXCERPT_CHARS + 80
    finally:
        svc.packages.cache_clear()


def test_package_without_full_text_degrades_to_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "PACKAGE_DIR", _write(tmp_path, comm_lines=False))
    svc.packages.cache_clear()
    try:
        p = svc.packages()[0]
        assert _ex(p, "相似法與相似法為同類因謂善五蘊") == []
        assert svc.available()[0]["excerpts"] is False
    finally:
        svc.packages.cache_clear()


def test_corpus_flags_packages_that_can_give_excerpts(pkg):
    assert svc.available()[0]["excerpts"] is True


@pytest.mark.anyio
async def test_excerpts_endpoint(pkg, monkeypatch):
    from app.api import commentary as api
    from app.database import get_db
    from app.main import app

    async def _no_db():
        yield None

    async def _fake_locate(_db, targets):
        return {t: ("urn:x", "https://fojin.app/texts/1/read?juan=1") for t in targets}

    monkeypatch.setattr(api, "_locate", _fake_locate)
    app.dependency_overrides[get_db] = _no_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/commentary/excerpts", params={"q": "相似法與相似法為同類因謂善五蘊"})
            assert r.status_code == 200
            body = r.json()
            assert body["matched"] is True and body["base_title"] == "阿毘達磨俱舍論"
            assert body["excerpts"][0]["line_from"] == "0100a05"
            assert body["excerpts"][0]["reader_url"].startswith("https://fojin.app/texts/")
            miss = (await c.get("/api/commentary/excerpts", params={"q": "般若波羅蜜多心經"})).json()
            assert miss["matched"] is False and miss["excerpts"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_quote_that_starts_mid_previous_line_is_not_cut_in_half(tmp_path, monkeypatch):
    # 宝疏实例：牒文「論「又此非一切至為同類因」」从上一行句号之后起
    mid = [list(r) for r in COMM]
    mid[3] = ["0100a04", "此下明第五同類因。論「謂相似法至為"]
    mid[4] = ["0100a05", "同類因」者，謂善與善等。相似法與相似法為同類因。"]
    monkeypatch.setattr(svc, "PACKAGE_DIR", _write(tmp_path, comm=mid))
    svc.packages.cache_clear()
    try:
        e = _ex(svc.packages()[0], "相似法與相似法為同類因謂善五蘊")[0]
        assert e["text"].startswith("論「謂相似法至為同類因」者")
        assert e["line_from"] == "0100a04" and e["anchor"] == f"{W}_p0100a04"
    finally:
        svc.packages.cache_clear()


def test_previous_line_ending_at_a_full_stop_adds_nothing(pkg):
    # 光记实例：上一行恰好以句号收尾，什么都不补
    e = _ex(pkg, "相似法與相似法為同類因謂善五蘊")[0]
    assert e["text"].startswith("相似法與相似法為同類因者")


def test_abbreviated_quote_with_zhi_is_kept_whole(tmp_path, monkeypatch):
    # 光记实例：牒文用「至」缩略（「謂前生至為同類因」者），4 字匹配落在后面的解释上；
    # 起点仍要回到牒文开头，不能从「答。」之后起把牒文切掉
    z = [list(r) for r in COMM]
    z[4] = ["0100a05", "「同類因至為同類因」者，答。謂相似法與相似法為同類因。"]
    monkeypatch.setattr(svc, "PACKAGE_DIR", _write(tmp_path, comm=z))
    svc.packages.cache_clear()
    try:
        e = _ex(svc.packages()[0], "相似法與相似法為同類因謂善五蘊")[0]
        assert e["text"].startswith("「同類因至為同類因」者，答。")
    finally:
        svc.packages.cache_clear()
