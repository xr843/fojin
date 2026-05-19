"""
extract_gaoseng_persons.py — Extract monk biographies from CBETA 高僧传 corpora.

Target corpora (CBETA TEI P5 XML):
    T2059  梁·慧皎《高僧传》          T/T50/T50n2059.xml   (~14 juan, ~500 bios)
    T2060  唐·道宣《续高僧传》        T/T50/T50n2060.xml   (~30 juan, ~700 bios)
    T2061  宋·赞宁《宋高僧传》        T/T50/T50n2061.xml   (~30 juan, ~660 bios)
    T2062  明·如惺《大明高僧传》      T/T50/T50n2062.xml   (~8 juan, ~110 bios)
    T2076  宋·道原《景德传灯录》      T/T51/T51n2076.xml   (~30 juan, ~1700 entries)
    X1565  宋·普济《五灯会元》        X/X80/X80n1565.xml   (~20 juan, ~1300 entries)

Data source: https://github.com/cbeta-org/xml-p5 (official CBETA TEI P5 mirror)
License:     CBETA copyright — non-commercial, attribution required.
             See https://www.cbeta.org/copyright.php

Pipeline outline (NOT implemented — scaffolding only):
    1. Download XML from GitHub raw to data/cbeta/.
    2. Parse TEI; split per biography by <cb:div type="other"> + <cb:mulu>.
    3. Flatten <p>/<lb> text; strip line-break markers; keep Taishō page refs.
    4. Chunk: one biography per LLM call (avg ~500-2000 chars, well under 8k).
    5. LLM structured extraction → JSON schema (see SCHEMA below).
    6. Validate, normalize names, cross-match with Wikidata QIDs.
    7. Upsert into fojin.persons with source=CBETA-T2059 etc.

Estimated scale:
    ~5000 biographies × ~1500 tokens in + ~400 tokens out
    ≈ 7.5M input + 2M output tokens
    Claude Haiku: ≈ $5 input + $5 output ≈ $10 total
    GPT-4o-mini:  ≈ $1.1 + $1.2 ≈ $2.5 total

Usage (planned):
    python extract_gaoseng_persons.py --work T2059 --limit 10 --dry-run
    python extract_gaoseng_persons.py --work all --out data/gaoseng_persons.jsonl
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CBETA_RAW = "https://raw.githubusercontent.com/cbeta-org/xml-p5/master"

WORKS: dict[str, dict] = {
    "T2059": {"path": "T/T50/T50n2059.xml", "title": "高僧传",     "author": "梁·慧皎",   "est_bios": 500},
    "T2060": {"path": "T/T50/T50n2060.xml", "title": "续高僧传",   "author": "唐·道宣",   "est_bios": 700},
    "T2061": {"path": "T/T50/T50n2061.xml", "title": "宋高僧传",   "author": "宋·赞宁",   "est_bios": 660},
    "T2062": {"path": "T/T50/T50n2062.xml", "title": "大明高僧传", "author": "明·如惺",   "est_bios": 110},
    "T2076": {"path": "T/T51/T51n2076.xml", "title": "景德传灯录", "author": "宋·道原",   "est_bios": 1700},
    "X1565": {"path": "X/X80/X80n1565.xml", "title": "五灯会元",   "author": "宋·普济",   "est_bios": 1300},
}

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0", "cb": "http://www.cbeta.org/ns/1.0"}

# ---------------------------------------------------------------------------
# Extraction schema (per monk biography)
# ---------------------------------------------------------------------------

SCHEMA = {
    "dharma_name":   "str  — 法名, e.g. 竺法蘭",
    "secular_name":  "str? — 俗姓/俗名",
    "aliases":       "list[str] — 别号/谥号",
    "dynasty":       "str  — 朝代 (梁/唐/宋/明...)",
    "birth_year":    "int? — 生年 (CE)",
    "death_year":    "int? — 卒年 (CE)",
    "age_at_death":  "int? — 世寿",
    "native_place":  "str? — 籍贯 (州/郡/县)",
    "ethnicity":     "str? — 汉/天竺/安息/月氏/西域...",
    "teachers":      "list[str] — 师承",
    "disciples":     "list[str] — 弟子",
    "residences":    "list[str] — 住锡寺院",
    "school":        "str? — 宗派 (禅/天台/华严/律/净土...)",
    "works":         "list[str] — 著作/译经",
    "key_events":    "list[str] — 大事记 (短句)",
    "source_ref":    "str  — Taishō page ref, e.g. T50.0322c01",
    "raw_text":      "str  — original biography text",
    "confidence":    "float — LLM self-reported 0-1",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Biography:
    work_id: str              # e.g. "T2059"
    juan: int                 # 卷号
    seq: int                  # 卷内序号
    title: str                # 目录标题
    raw_text: str             # 聚合后的正文
    page_ref: str             # Taishō 起始页 e.g. "T50.0322c01"

@dataclass
class ExtractedPerson:
    bio: Biography
    fields: dict = field(default_factory=dict)
    wikidata_qid: Optional[str] = None

# ---------------------------------------------------------------------------
# Pipeline stubs
# ---------------------------------------------------------------------------

def download_work(work_id: str, out_dir: Path) -> Path:
    """TODO: fetch {CBETA_RAW}/{WORKS[work_id]['path']} to out_dir, cache."""
    raise NotImplementedError

def iter_biographies(xml_path: Path, work_id: str) -> Iterator[Biography]:
    """TODO: parse TEI; yield one Biography per <cb:div type='other'> containing <cb:mulu>.

    Strategy:
        - Use lxml.etree.iterparse for memory efficiency.
        - Boundary: each <cb:div> whose direct child is <cb:mulu level='3'>.
        - Concat all descendant <p> text, strip <lb>, <note>, <pb>.
        - Capture first <lb n='...' ed='T'/> as page_ref.
    """
    raise NotImplementedError

PROMPT_TEMPLATE = """你是佛教文献专家。从下方《{work_title}》（{work_author}）单篇僧传中提取结构化信息。

要求：
1. 严格输出 JSON，不要 markdown 代码块。
2. 未知字段用 null 或 []；不要编造。
3. 年代用公历 CE 整数；朝代用单字（梁/唐/宋/明）。
4. 人名保留原文繁体。

输出 schema:
{schema_json}

僧传原文：
---
{bio_text}
---

JSON:"""

def build_prompt(bio: Biography) -> str:
    """TODO: render PROMPT_TEMPLATE with schema + bio_text."""
    raise NotImplementedError

def extract_one(bio: Biography) -> ExtractedPerson:
    """TODO: call LLM (Claude Haiku / GPT-4o-mini), parse JSON, validate."""
    raise NotImplementedError

def validate(person: ExtractedPerson) -> list[str]:
    """TODO: return list of validation errors.

    Rules:
        - dharma_name non-empty
        - birth_year <= death_year if both present
        - death_year within dynasty range (sanity)
        - age_at_death in [1, 130]
        - dynasty in known set
    """
    raise NotImplementedError

def match_wikidata(person: ExtractedPerson) -> Optional[str]:
    """TODO: SPARQL lookup by dharma_name + dynasty → QID. Fuzzy match fallback."""
    raise NotImplementedError

def upsert_db(person: ExtractedPerson) -> None:
    """TODO: INSERT INTO persons (...) ON CONFLICT DO UPDATE; source=CBETA-{work_id}."""
    raise NotImplementedError

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """TODO: argparse --work, --limit, --out, --dry-run, --resume."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
