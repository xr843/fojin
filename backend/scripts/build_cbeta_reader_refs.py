#!/usr/bin/env python3
"""从 CBETA xml-p5 提取阅读器需要的两份参考数据（只读 XML，不碰数据库）：

1. 册号/文件名：每部经每一卷对应的 CBETA 文件主名（如 T08n0235），用于
   - 生成 CBETA 标准引用 `(CBETA, T08, no. 235, p. 749a5-7)`；
   - 显示行首 `T08n0235_p0749a05`。
   text_line_anchors 只存了页栏行（0749a05），没有册号——跨册的经（同一部经分在几册）必须按卷取。
2. 目次（cb:mulu）：品/分/会等结构，每条记 [层级, 标题, 卷号, 该条之后第一个行号]。

文件选取与 import_content 完全一致（app.core.xml_parser.find_all_xml_files），保证与库里的
行号同源。只处理 --ids 里给出的经（默认：库里有行号的经，见 --ids-file）。

产物（前端静态文件，阅读器按需拉取，不进数据库）：
- frontend/public/cbeta-refs/stems.json：{经号: 文件主名 | [[起始卷, 文件主名], ...]}
- frontend/public/cbeta-toc/<经号>.json：[[层级, 标题, 卷, 行号], ...]（只有带目次的经才有文件）
  纯数字标题（如俱舍论「分別界品」下的「1」「2」，只是品内按卷的分段）不收：对读者没有信息量。

用法：python scripts/build_cbeta_reader_refs.py --xml-dir /path/to/xml-p5 --ids-file anchored_ids.json \
        --out-dir ../frontend/public
ids-file：库里有行号（text_line_anchors）的经号列表，JSON 数组。
"""

import argparse
import json
import re
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.xml_parser import find_all_xml_files

TEI = "{http://www.tei-c.org/ns/1.0}"
CB = "{http://www.cbeta.org/ns/1.0}"
STEM_RE = re.compile(r"^([A-Z]+\d+n[A-Za-z]?\d+[a-z]?)(?:_\d+)?$")


def scan_file(path: Path):
    """Yield ('juan', n) / ('mulu', level, title) / ('lb', n) in document order."""
    for _, el in etree.iterparse(str(path), events=("start",), huge_tree=True):
        tag = el.tag
        if tag == f"{TEI}milestone" and el.get("unit") == "juan":
            yield ("juan", int(el.get("n")))
        elif tag == f"{CB}mulu":
            if el.get("type") == "卷":
                continue
            title = "".join(el.itertext()).strip()
            level = int(el.get("level") or 1)
            if title and not title.replace(" ", "").isdigit():
                yield ("mulu", level, title)
        elif tag == f"{TEI}lb" and (not el.get("ed") or el.get("ed", "").startswith(("T", "X"))):
            n = el.get("n")
            if n:
                yield ("lb", n)


def build(cbeta_id: str, xml_dir: str):
    files = find_all_xml_files(cbeta_id, xml_dir)
    if not files:
        return None, None
    stems: list[list] = []  # [[first_juan, stem], ...]
    toc: list[list] = []  # [[level, title, juan, line_ref], ...]
    seen_juans: set[int] = set()
    for f in files:
        m = STEM_RE.match(f.stem)
        if not m:
            continue
        stem = m.group(1)
        juan = None
        pending: list[list] = []
        for ev in scan_file(f):
            if ev[0] == "juan":
                juan = ev[1]
                if juan not in seen_juans:
                    seen_juans.add(juan)
                    if not stems or stems[-1][1] != stem:
                        stems.append([juan, stem])
            elif ev[0] == "mulu":
                pending.append([ev[1], ev[2], juan])
            elif ev[0] == "lb" and pending:
                for p in pending:
                    toc.append([p[0], p[1], p[2] if p[2] is not None else juan, ev[1]])
                pending = []
    return stems, toc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml-dir", required=True)
    ap.add_argument("--ids-file", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    with open(a.ids_file) as fh:
        ids = json.load(fh)
    vols: dict[str, object] = {}
    tocs: dict[str, list] = {}
    for i, cid in enumerate(ids):
        stems, toc = build(cid, a.xml_dir)
        if not stems:
            print(f"no xml for {cid}", file=sys.stderr)
            continue
        vols[cid] = stems[0][1] if len(stems) == 1 else stems
        if toc:
            tocs[cid] = toc
        if i % 500 == 0:
            print(f"{i}/{len(ids)}", file=sys.stderr)
    out = Path(a.out_dir)
    (out / "cbeta-refs").mkdir(parents=True, exist_ok=True)
    (out / "cbeta-refs" / "stems.json").write_text(
        json.dumps(vols, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )
    toc_dir = out / "cbeta-toc"
    toc_dir.mkdir(parents=True, exist_ok=True)
    for old in toc_dir.glob("*.json"):
        old.unlink()
    for cid, toc in tocs.items():
        (toc_dir / f"{cid}.json").write_text(json.dumps(toc, ensure_ascii=False, separators=(",", ":")))
    print(f"stems {len(vols)} / toc {len(tocs)} texts, {sum(len(t) for t in tocs.values())} entries", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
