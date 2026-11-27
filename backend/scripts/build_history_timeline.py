"""佛教史长卷（/history）的人物数据：DILA 人名规范库 + 核心名单 → frontend/public/history-people.json

数据来源：法鼓文理学院 DILA「佛學規範資料庫」人名、地名两库
  https://github.com/DILA-edu/Authority-Databases （CC BY-SA 3.0 Unported，须署名、相同方式共享）
核心名单：backend/scripts/history_core_people.tsv（按 DILA 编号逐位指定——同名极多，绝不按名字匹配）

需要连生产库（只读）：把每位的本传 CBETA 行首换算成阅读页链接（经号→text_id，行首→卷号），
把藏内著译（T1837 等）换算成佛津的经典链接。按惯例在一次性容器里跑：

  docker run --rm --network <net> --env-file /home/admin/fojin/.env \\
    -v /home/admin/fojin/backend:/app:ro -v /tmp/hist:/work \\
    <backend image> python scripts/build_history_timeline.py /work/person.xml /work/history-people.json /work/place.xml

再把输出拷回仓库 frontend/public/history-people.json 提交。
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

NS = "{http://www.tei-c.org/ns/1.0}"
XML_NS = "{http://www.w3.org/XML/1998/namespace}"
CORE = pathlib.Path(__file__).with_name("history_core_people.tsv")

# 本传优先取这些僧传/灯录（DILA 的 listBibl 里还有大量方志、语录的零星提及）
BIO_WORKS = ("高僧傳", "續高僧傳", "宋高僧傳", "大明高僧傳", "補續高僧傳", "比丘尼傳", "景德傳燈錄",
             "五燈會元", "佛祖統紀", "出三藏記集", "新續高僧傳", "南宋元明禪林僧寶傳", "禪林僧寶傳",
             "續傳燈錄", "五燈全書", "淨土聖賢錄", "居士傳", "釋門正統", "大唐大慈恩寺三藏法師傳")
MAX_BIOS = 4
MAX_WORKS = 12
BIO_LEN = 220


def _year(s: str | None) -> int | None:
    m = re.search(r"([+-])(\d{4})", s or "")
    if not m:
        return None
    y = int(m.group(2))
    return -y if m.group(1) == "-" else y


def _span(el) -> list[int] | None:
    """DILA 的生卒是区间（「+0602-02-01 ~ +0603-02-18」），保留 [最早, 最晚] 两个年份。"""
    if el is None:
        return None
    ys = [_year(x) for x in re.findall(r"[+-]\d{4}", el.text or "")]
    ys = [y for y in ys if y is not None]
    if not ys:
        ys = [y for y in (_year(el.get("notBefore")), _year(el.get("notAfter"))) if y is not None]
    return [min(ys), max(ys)] if ys else None


def _clean_bio(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    # 去掉文末的出处括注（佛光：2024；疑年錄：99；http://…），正文里的年份括注保留
    s = re.sub(r"[（(][^（）()]*(?:http|佛光|佛百|疑年|望月|索引|：\d)[^（）()]*[）)]", "", s)
    return s[:BIO_LEN] + ("…" if len(s) > BIO_LEN else "")


def parse_dila(path: str, wanted: set[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != NS + "person":
            continue
        pid = el.get(XML_NS + "id")
        if pid not in wanted:
            el.clear()
            continue
        names = [(n.get(XML_NS + "lang") or "", n.get("type"), "".join(n.itertext()).strip()) for n in el.findall(NS + "persName")]
        main = next((n for lang, ty, n in names if ty is None and lang.startswith("zho")), names[0][2] if names else pid)
        rec: dict = {
            "id": pid,
            "name": main,
            "alt": [n for lang, _, n in names if n != main and lang.startswith("zho")],
            "birth": _span(el.find(NS + "birth")),
            "death": _span(el.find(NS + "death")),
            "relations": [(r.get("type"), r.get("active") if r.get("active") != pid else r.get("passive"))
                          for r in el.iter(NS + "relation")],
            "bibl": [re.sub(r"\s+", " ", "".join(b.itertext())).strip() for b in el.findall(f"{NS}listBibl/{NS}bibl")],
        }
        for n in el.findall(NS + "note"):
            ty = n.get("type")
            text = "".join(n.itertext())
            if ty == "dynasty":
                rec["dynasty"] = re.sub(r"\s+", " ", text).strip()
            elif ty == "monk":
                rec["monk"] = text.strip() == "是"
            elif ty == "concise":
                rec["bio"] = _clean_bio(text)
            elif ty == "worksInTripitaka":
                rec["works"] = [w.strip() for w in text.split("\n") if w.strip()]
        # 籍贯 / 葬地：DILA 地名规范库编号（PL…），坐标在 load_places 里补
        for ty, key in (("placeOfOrigin", "origin"), ("placeOfBurial", "burial")):
            note = next((n for n in el.findall(NS + "note") if n.get("type") == ty), None)
            pn = note.find(NS + "placeName") if note is not None else None
            ref = pn.find(NS + "ref") if pn is not None else None
            if pn is not None and ref is not None and (ref.text or "").startswith("PL"):
                rec[key] = ((pn.text or "").strip(), ref.text.strip())
        sex = el.find(NS + "sex")
        rec["female"] = sex is not None and sex.get("value") == "2"
        occ = el.find(NS + "occupation")
        rec["translator"] = bool(occ is not None and occ.text and "譯" in occ.text)
        out[pid] = rec
        el.clear()
    return out


_LINE_HEAD = re.compile(r"\b([A-Z]{1,2})(\d{2,3})n(\d{4}[a-zA-Z]?)_p(\d{4}[abc]\d{2})")
_WORK_ID = re.compile(r"\(([A-Z]{1,2}\d{4}[a-zA-Z]?)\)\s*$")


_VARIANTS = str.maketrans({"鑒": "鑑", "峯": "峰", "菴": "庵", "巖": "岩", "旡": "無"})


def _fold(s: str) -> str:
    """传题与人名的常见异体字归一（「鑒真傳」对「鑑真」）。"""
    return s.translate(_VARIANTS)


def _cbeta_id(canon: str, no: str) -> str:
    return f"{canon}{no}"


async def resolve(people: dict[str, dict]) -> None:
    """本传行首 → 阅读页链接；著译经号 → 经典页链接。生产库只读。"""
    from sqlalchemy import text as sql

    from app.database import async_session
    from app.services.urn import reader_path

    async with async_session() as db:
        ids = {r[0]: r[1] for r in (await db.execute(sql("SELECT cbeta_id, id FROM buddhist_texts WHERE cbeta_id IS NOT NULL"))).all()}

        async def juan_of(text_id: int, ref: str) -> int | None:
            row = await db.execute(sql(
                "SELECT juan_num FROM text_line_anchors WHERE text_id=:t AND line_ref<=:r ORDER BY line_ref DESC LIMIT 1"),
                {"t": text_id, "r": ref})
            j = row.scalar_one_or_none()
            if j is None:
                row = await db.execute(sql(
                    "SELECT juan_num FROM text_line_anchors WHERE text_id=:t AND line_ref>:r ORDER BY line_ref ASC LIMIT 1"),
                    {"t": text_id, "r": ref})
                j = row.scalar_one_or_none()
            return j

        for p in people.values():
            names = {p["name"], *p["alt"], *([p["display"]] if p.get("display") else [])}
            names = {n for n in names if len(n) >= 2}

            def own(title: str, names: set[str] = names) -> bool:
                """本传：传题（「書名: 某某傳」冒号后）里有本人名字；整部专传（如慈恩傳）书名里有名字。
                DILA 的 listBibl 多数条目是「在别人的传里被提到」，那些只算「提及」。"""
                head = title.split("{")[0]
                part = head.split(":", 1)[1] if ":" in head else head
                return any(_fold(n) in _fold(part) for n in names)

            bios, mentions, seen = [], [], set()
            ranked = sorted(p["bibl"], key=lambda b: next((i for i, w in enumerate(BIO_WORKS) if w in b), 99))
            for b in ranked:
                m = _LINE_HEAD.search(b)
                if not m:
                    continue
                canon, _vol, no, ref = m.groups()
                tid = ids.get(_cbeta_id(canon, no))
                title = re.sub(r"^\(\s*CBETA\s+\S+\s*\)\s*", "", b).strip()
                if tid is None or not title:
                    continue
                is_own = own(title)
                bucket = bios if is_own else mentions
                # 本传同一部书只取一处（宋高僧傳里「慧能傳」「釋慧能傳」是同一篇的两个标目）
                key = (is_own, title.split(":")[0].strip() if is_own else title.split("{")[0].strip())
                if key in seen or len(bucket) >= (MAX_BIOS if is_own else 2):
                    continue
                juan = await juan_of(tid, ref)
                if juan is None:
                    continue
                seen.add(key)
                label = re.sub(r"\s*\{[^}]*\}", "", title)
                bucket.append({"t": re.sub(r"\s*:\s*", " · ", label).strip(), "u": reader_path(tid, juan, f"p{ref}"),
                               "lh": f"{canon}{_vol}n{no}_p{ref}"})
            p["bios"] = bios
            p["mentions"] = mentions if not bios else []
            works = []
            for w in p.get("works", []):
                m = _WORK_ID.search(w)
                if not m:
                    continue
                cid = m.group(1)
                tid = ids.get(cid)
                if tid is None:
                    continue
                works.append({"t": w[: m.start()].strip(), "c": cid, "u": f"/texts/{tid}"})
                if len(works) >= MAX_WORKS:
                    break
            p["works_n"] = len(p.get("works", []))
            p["works"] = works


SCHOOLS = ("译经", "三论", "义学", "天台", "华严", "唯识", "律", "净土", "禅", "密", "其他")


def load_core() -> list[tuple[str, str, str, bool]]:
    """核心名单：编号、显示名、宗派泳道、是否比丘尼（备注列含「比丘尼」；见 tsv 文件头）。"""
    rows = []
    for line in CORE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = [c.strip() for c in line.split("\t")] + ["", ""]
        if cols[2] not in SCHOOLS:
            sys.exit(f"{cols[0]} 的宗派「{cols[2]}」不在 {SCHOOLS} 里")
        rows.append((cols[0], cols[1], cols[2], "比丘尼" in cols[3]))
    return rows


def load_places(path: str) -> dict[str, tuple[float, float, str]]:
    """DILA 地名规范库（authority_place，同为 CC BY-SA 3.0）：PL 编号 → (经度, 纬度, 可信度)。"""
    out: dict[str, tuple[float, float, str]] = {}
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != NS + "place":
            continue
        geo = el.find(f"{NS}location/{NS}geo")
        if geo is not None and (geo.text or "").strip():
            lon, lat = (float(x) for x in geo.text.split()[:2])
            out[el.get(XML_NS + "id")] = (lon, lat, geo.get("cert") or "")
        el.clear()
    return out


def build(xml_path: str, out_path: str, place_path: str | None = None) -> None:
    core = load_core()
    people = parse_dila(xml_path, {row[0] for row in core})
    for pid, display, *_ in core:
        if pid in people:
            people[pid]["display"] = display
    missing = [row[0] for row in core if row[0] not in people]
    if missing:
        sys.exit(f"DILA 里找不到这些编号：{missing}")
    asyncio.run(resolve(people))
    places = load_places(place_path) if place_path else {}
    inset = set(people)
    result = []
    for pid, display, school, nun in core:
        p = people[pid]
        teachers = sorted({o for ty, o in p["relations"] if ty == "teacher" and o in inset})
        students = sorted({o for ty, o in p["relations"] if ty == "student" and o in inset})
        rec = {
            "id": pid,
            "n": display or p["name"],
            "dn": p["name"],
            "alt": [a for a in p["alt"] if a != display][:6],
            "dy": p.get("dynasty", ""),
            "sc": school,
            "b": p["birth"],
            "d": p["death"],
            # DILA 的「是否僧人」对比丘尼常缺（道儀），名单标了比丘尼的算出家人
            "monk": p.get("monk", False) or nun,
            **({"f": True} if p.get("female") else {}),
            **({"nun": True} if nun else {}),
            "tr": p["translator"],
            "bio": p.get("bio", ""),
            "te": teachers,
            "st": students,
            "bios": p["bios"],
            "men": p["mentions"],
            "works": p["works"],
            "wn": p["works_n"],
        }
        # 籍贯、葬地落到地图上：[经度, 纬度, 地名, 可信度]（坐标两位小数够用，文件小一半）
        for key, short in (("origin", "o"), ("burial", "bu")):
            if p.get(key) and p[key][1] in places:
                lon, lat, cert = places[p[key][1]]
                rec[short] = [round(lon, 3), round(lat, 3), p[key][0], cert]
        result.append(rec)
    # 师承只记了一边的，补成双向
    by = {r["id"]: r for r in result}
    for r in result:
        for t in r["te"]:
            if r["id"] not in by[t]["st"]:
                by[t]["st"].append(r["id"])
        for s in r["st"]:
            if r["id"] not in by[s]["te"]:
                by[s]["te"].append(r["id"])
    doc = {
        "source": "DILA 佛學規範資料庫·人名（法鼓文理學院）",
        "source_url": "https://authority.dila.edu.tw/person/",
        "license": "CC BY-SA 3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "people": result,
    }
    pathlib.Path(out_path).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    dated = sum(1 for r in result if r["b"] or r["d"])
    print(f"{len(result)} 人，有年份 {dated}，有本传链接 {sum(1 for r in result if r['bios'])}，只有提及 {sum(1 for r in result if r['men'])}，"
          f"有著译链接 {sum(1 for r in result if r['works'])}，师承连线 {sum(len(r['st']) for r in result)}，"
          f"籍贯上图 {sum(1 for r in result if r.get('o'))}，葬地上图 {sum(1 for r in result if r.get('bu'))}")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit("用法：build_history_timeline.py <DILA person.xml> <输出 json> [DILA place.xml]")
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
