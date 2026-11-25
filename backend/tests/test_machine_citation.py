"""机器可读引用（services/machine_citation.py、machine_citation_api.enrich_verdict）。"""

import asyncio
import json
from pathlib import Path

import pytest

from app.schemas.verification import QuoteMatch, QuoteVerdict
from app.services import machine_citation_api as mca
from app.services.machine_citation import (
    build_citation,
    format_line,
    license_for,
    normalize_line_ref,
    parse_line_head,
    parse_stem,
    stem_for,
)

REPO = Path(__file__).resolve().parents[2]


def test_backend_stems_copy_matches_frontend():
    # 两份册号表必须一致：前端阅读器的行首与开放接口给的行首不能各说各话
    front = REPO / "frontend" / "public" / "cbeta-refs" / "stems.json"
    back = REPO / "backend" / "app" / "data" / "cbeta_stems.json"
    if not front.exists():
        pytest.skip("frontend 不在（单独打包后端时）")
    assert json.loads(back.read_text()) == json.loads(front.read_text())


def test_stem_and_line_parsing():
    assert stem_for("T0374", 14) == "T12n0374"
    assert parse_stem("T12n0374") == ("T12", "374")
    assert parse_stem("T02n0128a") == ("T02", "128a")
    assert normalize_line_ref("p0450a12") == "0450a12"
    assert normalize_line_ref("0450a12") == "0450a12"
    assert normalize_line_ref("abc") is None
    assert format_line("0450a12") == "p. 450a12"
    assert parse_line_head("T12n0374_p0450a12") == ("T0374", "0450a12")
    assert parse_line_head("T12n0374") is None


def test_cross_volume_stem_uses_starting_juan():
    # 跨册的经按起始卷分段：A1561 卷 1–32 在 A120，卷 33 起在 A121
    assert stem_for("A1561", 1) == "A120n1561"
    assert stem_for("A1561", 32) == "A120n1561"
    assert stem_for("A1561", 33) == "A121n1561"


def test_plain_citation_matches_reader_copy_format():
    c = build_citation(
        cbeta_id="T0374",
        title="大般涅槃經",
        juan=14,
        fascicle_count=40,
        line_ref="0450a12",
        urn="fojin:cbeta/T0374.14#p0450a12",
        reader_url="https://fojin.app/texts/15/read?juan=14&anchor=p0450a12",
        translator="曇無讖",
        dynasty="北涼",
        quote="諸行無常 是生滅法",
    )
    # 与前端 formatCbetaCitation 同一写法；引文里的空白去掉
    assert c["plain"] == "《大般涅槃經》卷14：「諸行無常是生滅法」(CBETA, T12, no. 374, p. 450a12)"
    assert c["cbeta_line_head"] == "T12n0374_p0450a12"
    assert c["license"]["license"] == "CC BY-NC-SA 3.0 TW"
    assert c["license"]["commercial_use"] is False
    assert "title = {大般涅槃經}" in c["bibtex"] and "author = {[北涼] 曇無讖}" in c["bibtex"]
    assert c["ris"].startswith("TY  - BOOK") and c["ris"].endswith("ER  - ")
    assert c["csl_json"]["type"] == "book" and c["csl_json"]["URL"].endswith("p0450a12")


def test_single_fascicle_work_omits_juan_and_juan_level_has_no_line():
    c = build_citation(
        cbeta_id="T0235", title="金剛般若波羅蜜經", juan=1, fascicle_count=1, line_ref=None, urn=None, reader_url=None
    )
    assert c["plain"] == "《金剛般若波羅蜜經》(CBETA, T08, no. 235)"
    assert c["cbeta_line_head"] is None


def test_licenses_by_source():
    assert license_for("SC-mn10")["license"] == "CC0 1.0"
    assert "AI" in license_for("SC-mn10")["note"]  # 创办人请求不要用于 AI，照实告知
    assert license_for("84K-toh11")["license"] == "CC BY-NC-ND 4.0"
    assert license_for("GRETIL-x")["license"] == "NOT STATED"
    assert license_for("JB095")["license"] == "CC BY-NC-SA 3.0 TW"


class _Meta:
    title_zh = "大般涅槃經"
    fascicle_count = 40
    translator = "曇無讖"
    dynasty = "北涼"


def test_enrich_verdict_locates_first_matches_only(monkeypatch):
    calls = []

    async def fake_locate(db, text_id, juan, quote):
        calls.append(text_id)
        return ("p0450a12", 100, 108) if text_id == 15 else None

    async def fake_meta(db, text_id):
        return _Meta()

    monkeypatch.setattr(mca, "locate_quote", fake_locate)
    monkeypatch.setattr(mca, "_text_meta", fake_meta)
    matches = [
        QuoteMatch(
            text_id=15,
            cbeta_id="T0374",
            title_zh="大般涅槃經",
            juan_num=14,
            reader_url="https://fojin.app/texts/15/read?juan=14",
        ),
        QuoteMatch(
            text_id=16,
            cbeta_id="T0375",
            title_zh="大般涅槃經",
            juan_num=13,
            reader_url="https://fojin.app/texts/16/read?juan=13",
        ),
    ] + [QuoteMatch(text_id=100 + i, cbeta_id="T0001", juan_num=1) for i in range(3)]
    v = QuoteVerdict(
        quote="諸行無常是生滅法",
        normalised_quote="诸行无常是生灭法",
        verbatim=True,
        bucket="exact",
        similarity=1.0,
        matches=matches,
    )
    out = asyncio.run(mca.enrich_verdict(None, v))

    first = out.matches[0]
    assert first.line_ref == "0450a12" and first.cbeta_line_head == "T12n0374_p0450a12"
    assert first.line_urn == "fojin:cbeta/T0374.14#p0450a12"
    assert first.reader_url.endswith("anchor=p0450a12&hl=100-108")
    assert first.citation.startswith("《大般涅槃經》卷14：「諸行無常是生滅法」(CBETA, T12, no. 374, p. 450a12)")
    # 定位不到：保持卷级，不编行号
    assert out.matches[1].line_ref is None and out.matches[1].reader_url.endswith("juan=13")
    # 只给前 3 条读全文定位；全部都带许可
    assert len(calls) == mca.MAX_LOCATED_MATCHES
    assert all(m.license == "CC BY-NC-SA 3.0 TW" for m in out.matches)
    assert out.matches[4].citation is None
