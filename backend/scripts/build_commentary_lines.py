"""给经注对齐包补上注疏全文（按 CBETA 行），供「注疏怎么讲这几句」截取片段用。

    python backend/scripts/build_commentary_lines.py \
        --package kosa-T1558.v2.json --xml-root /path/to/cbeta/xml-p5 \
        --works T41n1821 T41n1822 --out kosa-T1558.v3.json

对齐包只带每条对齐点附近的一小段注文；要在两个对齐点之间按牒文截取，需要整部
注疏的逐行原文。原文取自 CBETA XML（CC BY-NC-SA 4.0），与包里已有文本同源。

产物不进仓库：对齐包以带外方式部署到 /data/commentary（见 services/commentary）。
**新包要替换旧包，不能并存**——packages() 会加载目录里的全部 *.json。
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://www.tei-c.org/ns/1.0}"
CB = "{http://www.cbeta.org/ns/1.0}"
# 不属于正文的元素：校勘异文、经号、目次、卷首信息、书末校注
_SKIP = {f"{NS}rdg", f"{CB}docNumber", f"{CB}mulu", f"{NS}teiHeader", f"{NS}back"}


def commentary_lines(xml_path: Path) -> list[list[str]]:
    """[[行标, 该行正文], ...]，按书中顺序。行标形如 0002c14（与包里锚点的 _p 后半一致）。

    夹注（note place="inline"）是正文的一部分，保留；其余 note 是校勘记，跳过。
    """
    body = ET.parse(xml_path).getroot().find(f".//{NS}text")
    if body is None:
        raise ValueError(f"{xml_path}: no <text>")
    texts: dict[str, list[str]] = {}
    order: list[str] = []
    cur: list[str | None] = [None]

    def add(t: str | None) -> None:
        if t and cur[0] is not None:
            texts[cur[0]].append(t)

    def walk(el: ET.Element) -> None:
        if el.tag == f"{NS}lb":
            n = el.get("n")
            # 只认本书自己的行号（同一行可能另有别本的 lb，ed 不同）
            if n and el.get("ed") in (None, "T", "X", "ZW"):
                if n not in texts:
                    texts[n] = []
                    order.append(n)
                cur[0] = n
            add(el.tail)
            return
        if (el.tag == f"{NS}note" and el.get("place") != "inline") or el.tag in _SKIP:
            add(el.tail)
            return
        add(el.text)
        for ch in el:
            walk(ch)
        add(el.tail)

    walk(body)
    return [[n, "".join(texts[n]).strip()] for n in order]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--package", required=True, type=Path)
    ap.add_argument("--xml-root", required=True, type=Path, help="CBETA xml-p5 根目录")
    ap.add_argument("--works", nargs="+", required=True, help="CBETA 全号，如 T41n1821")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()

    pkg = json.loads(a.package.read_text(encoding="utf-8"))
    pkg.setdefault("commentary_lines", {})
    for work in a.works:
        canon = work.split("n")[0]  # T41
        path = a.xml_root / canon[0] / canon / f"{work}.xml"
        lines = commentary_lines(path)
        anchors = {n["anchor"].rsplit("_p", 1)[-1] for n in pkg["notes"] if n["work"] == work}
        have = {ref for ref, _ in lines}
        missing = anchors - have
        if missing:
            raise SystemExit(f"{work}: {len(missing)} 个对齐点的行号在原文里找不到，例如 {sorted(missing)[:3]}")
        pkg["commentary_lines"][work] = lines
        chars = sum(len(t) for _, t in lines)
        print(f"{work}: {len(lines)} 行 / {chars} 字；对齐点 {len(anchors)} 个全部落在原文行上")
    pkg["meta"]["schema"] = max(int(pkg["meta"].get("schema", 1)), 2)
    a.out.write_text(json.dumps(pkg, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"写出 {a.out}（{a.out.stat().st_size / 1e6:.1f} MB）")


if __name__ == "__main__":
    main()
