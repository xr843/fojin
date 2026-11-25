"""机器可读引用：行级 CBETA 引用、各来源许可、论文引用格式（2026-11-25）。

给不访问佛津网站的开发者与 AI agent 用：拿到一处经文位置（URN 或 CBETA 行首），就能得到
  - 可直接粘贴的中文引用（与阅读器「复制引用」同一写法：《經名》卷N：(CBETA, T12, no. 374, p. 450a12)）；
  - CBETA 行首 T12n0374_p0450a12（学界通用写法）与行级 URN fojin:cbeta/T0374.14#p0450a12；
  - BibTeX / RIS / CSL-JSON；
  - **这段文字的许可与署名要求**——下游应用必须知道 CBETA 是「署名-非商业-相同方式共享」，
    基础设施不说清楚，等于把合规风险转嫁给开发者。许可文字以仓库根目录 NOTICE 为准，改这里要同步改那里。

册号（T12）来自 app/data/cbeta_stems.json，与前端 public/cbeta-refs/stems.json 是同一份
（scripts/build_cbeta_reader_refs.py 同时写两处；tests/test_machine_citation.py 比对一致）。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_STEMS_PATH = Path(__file__).resolve().parent.parent / "data" / "cbeta_stems.json"
_STEM_RE = re.compile(r"^([A-Z]+)(\d+)n([A-Za-z]?)(\d+)([a-z]?)$")
_LINE_RE = re.compile(r"^p?(\d{4})([a-z])(\d{2})$")
_LINE_HEAD_RE = re.compile(r"^([A-Z]+\d+n[A-Za-z]?\d+[a-z]?)_p(\d{4}[a-z]\d{2})$")

# ---------- 许可（与 NOTICE 一致） ----------
LICENSES: dict[str, dict] = {
    "cbeta": {
        "source": "CBETA",
        "license": "CC BY-NC-SA 3.0 TW",
        "license_url": "https://creativecommons.org/licenses/by-nc-sa/3.0/tw/",
        "attribution": "CBETA 中華電子佛典協會（https://cbeta.org）",
        "commercial_use": False,
        "conditions": [
            "署名 CBETA",
            "不得商业使用",
            "改作须以相同许可分享",
            "CBETA 使用說明：转载以不改变实质内容为原则，并需于成品附上 CBETA 说明及版本资讯",
        ],
        "not_covered": "《印順法師佛學著作集》《太虛大師全書》等另有著作权，不在 CBETA 的 CC 授权内（佛津未收录）",
    },
    "84000": {
        "source": "84000: Translating the Words of the Buddha",
        "license": "CC BY-NC-ND 4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
        "attribution": "84000（https://84000.co）",
        "commercial_use": False,
        "conditions": [
            "署名 84000",
            "不得商业使用",
            "不得改作；不得在删去注释的情况下整篇转载译文（逐字摘引属合理引用）",
        ],
        "note": "84000 使用条款页标为草稿（2026-05-15），引用前请复核",
    },
    "suttacentral": {
        "source": "SuttaCentral",
        "license": "CC0 1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "attribution": "SuttaCentral（https://suttacentral.net）——CC0 不要求署名，佛津出于礼貌署名",
        "commercial_use": True,
        "conditions": [],
        "note": (
            "SuttaCentral 创办人曾公开请求不要将其文本用于 AI / 聊天机器人；这是请求而非许可条款，"
            "见 https://discourse.suttacentral.net/t/33374"
        ),
    },
    "gretil": {
        "source": "GRETIL",
        "license": "NOT STATED",
        "license_url": None,
        "attribution": "GRETIL（https://gretil.sub.uni-goettingen.de）",
        "commercial_use": None,
        "conditions": ["许可未声明；逐篇条款未知，转载前请联系 gretil@sub.uni-goettingen.de"],
    },
}


def source_of(cbeta_id: str | None) -> str:
    """按编号前缀判断全文来自哪个来源（佛津只有这四个来源存全文）。"""
    cid = cbeta_id or ""
    if cid.startswith("SC-"):
        return "suttacentral"
    if cid.startswith("84K-"):
        return "84000"
    if cid.startswith("GRETIL-"):
        return "gretil"
    return "cbeta"


def license_for(cbeta_id: str | None) -> dict:
    return LICENSES[source_of(cbeta_id)]


# ---------- 册号与行号 ----------
@lru_cache(maxsize=1)
def _stems() -> dict:
    return json.loads(_STEMS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _stem_to_id() -> dict[str, str]:
    out: dict[str, str] = {}
    for cid, v in _stems().items():
        for stem in [v] if isinstance(v, str) else [s for _, s in v]:
            out.setdefault(stem, cid)
    return out


def stem_for(cbeta_id: str | None, juan: int | None) -> str | None:
    """某经某卷所在的 CBETA 文件主名，如 T12n0374；跨册的经按起始卷分段。查不到返回 None。"""
    v = _stems().get(cbeta_id or "")
    if not v:
        return None
    if isinstance(v, str):
        return v
    hit = None
    for start, stem in v:
        if (juan or 1) >= start:
            hit = stem
        else:
            break
    return hit or v[0][1]


def parse_stem(stem: str) -> tuple[str, str] | None:
    """T12n0374 → ("T12", "374")；T02n0128a → ("T02", "128a")。"""
    m = _STEM_RE.match(stem)
    if not m:
        return None
    coll, vol, prefix, num, suffix = m.groups()
    return f"{coll}{vol}", f"{prefix}{int(num)}{suffix}"


def normalize_line_ref(ref: str | None) -> str | None:
    """p0450a12 / 0450a12 → 0450a12；不像行号返回 None。"""
    if not ref:
        return None
    m = _LINE_RE.match(ref)
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else None


def format_line(ref: str) -> str:
    """0450a12 → p. 450a12（CBETA 书目写法去前导零）。"""
    m = _LINE_RE.match(ref)
    return f"p. {int(m.group(1))}{m.group(2)}{int(m.group(3))}" if m else ref


def parse_line_head(head: str) -> tuple[str, str] | None:
    """CBETA 行首 T12n0374_p0450a12 → (cbeta_id "T0374", line_ref "0450a12")。"""
    m = _LINE_HEAD_RE.match(head.strip())
    if not m:
        return None
    cid = _stem_to_id().get(m.group(1))
    return (cid, m.group(2)) if cid else None


# ---------- 引用格式 ----------
def _bib_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def build_citation(
    *,
    cbeta_id: str | None,
    title: str,
    juan: int | None,
    fascicle_count: int | None,
    line_ref: str | None,
    urn: str | None,
    reader_url: str | None,
    translator: str | None = None,
    dynasty: str | None = None,
    quote: str | None = None,
) -> dict:
    """组装一处引用的全部机器可读形式。line_ref 为 None 时只到卷。"""
    src = source_of(cbeta_id)
    lic = LICENSES[src]
    ref = normalize_line_ref(line_ref)
    juan_part = f"卷{juan}" if juan and (fascicle_count or 0) != 1 else ""

    stem = stem_for(cbeta_id, juan) if src == "cbeta" else None
    parsed = parse_stem(stem) if stem else None
    loc: list[str] = []
    line_head = None
    if src == "cbeta":
        loc.append("CBETA")
        if parsed:
            loc += [parsed[0], f"no. {parsed[1]}"]
            if ref:
                loc.append(format_line(ref))
                line_head = f"{stem}_p{ref}"
        else:
            loc.append(cbeta_id or "")
    else:
        loc += [lic["source"], cbeta_id or ""]
    loc_str = ", ".join(x for x in loc if x)
    q = re.sub(r"\s+", "", quote) if quote else ""
    plain = f"《{title}》{juan_part}" + (f"：「{q}」" if q else "") + f"({loc_str})"

    author = " ".join(x for x in (f"[{dynasty}]" if dynasty else "", translator or "") if x).strip() or None
    note = ", ".join(x for x in (juan_part, loc_str) if x)
    key = re.sub(r"[^A-Za-z0-9]", "", f"fojin{cbeta_id or ''}{juan or ''}{ref or ''}") or "fojin"
    bib_lines = [f"@book{{{key},", f"  title = {{{_bib_escape(title)}}},"]
    if author:
        bib_lines.append(f"  author = {{{_bib_escape(author)}}},")
    bib_lines += [
        f"  publisher = {{{_bib_escape(lic['source'])}}},",
        f"  note = {{{_bib_escape(note)}}},",
    ]
    if reader_url:
        bib_lines.append(f"  url = {{{reader_url}}},")
    bib_lines.append("}")

    ris_lines = ["TY  - BOOK", f"TI  - {title}"]
    if author:
        ris_lines.append(f"AU  - {author}")
    ris_lines += [f"PB  - {lic['source']}", f"N1  - {note}"]
    if reader_url:
        ris_lines.append(f"UR  - {reader_url}")
    if urn:
        ris_lines.append(f"ID  - {urn}")
    ris_lines.append("ER  - ")

    csl = {
        "id": urn or key,
        "type": "book",
        "title": title,
        "publisher": lic["source"],
        "note": note,
    }
    if author:
        csl["author"] = [{"literal": author}]
    if reader_url:
        csl["URL"] = reader_url

    return {
        "urn": urn,
        "reader_url": reader_url,
        "cbeta_id": cbeta_id,
        "title": title,
        "juan": juan,
        "line_ref": ref,
        "cbeta_line_head": line_head,
        "plain": plain,
        "bibtex": "\n".join(bib_lines),
        "ris": "\n".join(ris_lines),
        "csl_json": csl,
        "license": lic,
    }
