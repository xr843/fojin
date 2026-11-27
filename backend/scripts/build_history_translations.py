"""佛教史长卷「译经长河」数据：《开元释教录》逐部记下的译出年份。

《开元释教录》（T2154，唐智昇撰）卷 1–10「总括群经录」按朝代、译人列出每部经，部名下夹注常写
「弘始五年四月二十三日出」这样的译出时间。本脚本：

1. 逐条抽出夹注里第一处「年号＋第几年（＋干支）」；
2. 用 DILA 时间规范库（authority_time，CC BY-SA 3.0）把年号换成公元年——同名年号（太和、永平……）
   按本朝代段的断代、夹注里写明的朝代（「符秦建元十二年」）、干支三样挑；挑不出唯一一个就不记；
3. 「右……部……卷。」后面那句是译人（沙門鳩摩羅什。秦言童壽……），按它归属本组各部；
4. 经名＋译人对上佛津藏内经典的，带阅读页链接。

去掉：「今移在某錄」「總刪之」「不錄」之类改隶/删除的互见条目（同一部经别处另有正条）。

2026-11-27 实测：2,193 部里 467 部夹注有年号，460 部换算成唯一公元年；去互见后 453 部，268 部对上藏内经典。
随机抽 40 条逐条核对，年份 40/40 对、全部是译出（或撰出）时间。

用法（DILA 年号库下载自 github.com/DILA-edu/Authority-Databases 的 authority_time/SQL/authority_time_chinese.sql；
T55n2154.xml 在服务器 /home/admin/fojin/data/xml-p5/T/T55/；texts.tsv 是生产库导出，见下）：

    psql -At -F $'\\t' -c "select id,cbeta_id,title_zh,coalesce(translator,'') from buddhist_texts
        where cbeta_id ~ '^T[0-9]' and lang='lzh'" > texts.tsv
    python build_history_translations.py authority_time_chinese.sql T55n2154.xml texts.tsv \\
        ../../frontend/public/history-translations.json
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

KAIYUAN_CBETA = "T2154"

# ---------- DILA 年号库：年号 + 第几年 → 公元年 ----------


def _sql_rows(sql: str, table: str) -> list[list[str]]:
    out = []
    for body in re.findall(r"INSERT INTO `" + table + r"` VALUES (.*?);\n", sql, re.S):
        for tup in re.findall(r"\((.*?)\)(?=,\(|$)", body):
            out.append([x.strip("'") for x in re.findall(r"'(?:[^'\\]|\\.)*'|[^,]+", tup)])
    return out


def _jd_to_year(jd: int) -> int:
    """儒略日 → 公历年（1582 年前用儒略历）"""
    f = jd + 1401 + (((4 * jd + 274277) // 146097) * 3) // 4 - 38 if jd >= 2299161 else jd + 1401
    e = 4 * f + 3
    h = 5 * ((e % 1461) // 4) + 2
    m = (h // 153 + 2) % 12 + 1
    return e // 1461 - 4716 + (12 + 2 - m) // 12


def load_eras(sql_path: str) -> dict[str, list[dict]]:
    """{年号名: [{rank, dyn:[朝代名], years:{第几年: 公元年}}]}，只取中国年号；某年的公元年取该年正月初一"""
    sql = Path(sql_path).read_text(encoding="utf8")
    era_names = collections.defaultdict(list)
    for r in _sql_rows(sql, "t_era_names"):
        era_names[r[1]].append((int(r[0]), int(r[2])))
    era_emp = {int(a): int(b) for a, b in _sql_rows(sql, "t_era")}
    emp_dyn = {int(r[0]): int(r[1]) for r in _sql_rows(sql, "t_emperor")}
    dyn_names = collections.defaultdict(list)
    for r in _sql_rows(sql, "t_dynasty_names"):
        dyn_names[int(r[0])].append(r[1])
    dyn_type = {int(r[0]): r[1] for r in _sql_rows(sql, "t_dynasty")}
    first: dict[tuple[int, int], int] = {}
    for r in _sql_rows(sql, "t_month"):
        k = (int(r[5]), int(r[1]))
        first[k] = min(first.get(k, int(r[6])), int(r[6]))
    by_era = collections.defaultdict(dict)
    for (eid, y), jd in first.items():
        by_era[eid][y] = _jd_to_year(jd)
    out: dict[str, list[dict]] = {}
    for name, ids in era_names.items():
        for eid, rank in ids:
            d = emp_dyn.get(era_emp.get(eid))
            if d is None or dyn_type.get(d) != "chinese" or eid not in by_era:
                continue
            out.setdefault(name, []).append({"rank": rank, "dyn": dyn_names[d][:3], "years": by_era[eid]})
    return out


# ---------- 中文数字、干支 ----------

_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn(s: str) -> int:
    if s == "元":
        return 1
    tot = cur = 0
    for ch in s:
        if ch == "百":
            tot += (cur or 1) * 100
            cur = 0
        elif ch == "十":
            tot += (cur or 1) * 10
            cur = 0
        else:
            cur = _NUM.get(ch, 0)
    return tot + cur


def ganzhi(y: int) -> str:
    return "甲乙丙丁戊己庚辛壬癸"[(y - 4) % 10] + "子丑寅卯辰巳午未申酉戌亥"[(y - 4) % 12]


# ---------- 开元录朝代段 ----------

# 朝代段的通行断代：只用来在同名年号里挑对的那个（经录自己的「起…至…」有几处与年号库对不上，如後秦永和库里只一年）
SPAN = {
    "後漢": (67, 220), "曹魏": (220, 265), "孫吳": (222, 280), "西晉": (265, 317), "東晉": (317, 420),
    "前涼": (301, 376), "苻秦": (351, 394), "姚秦": (384, 417), "西秦": (385, 431), "北涼": (397, 439),
    "劉宋": (420, 479), "蕭齊": (479, 502), "前梁": (502, 587), "後魏": (386, 557), "高齊": (550, 577),
    "周": (557, 581), "陳": (557, 589), "隋": (581, 618), "大唐": (618, 730), "大唐傳譯之餘": (618, 730),
}  # fmt: skip
# 朝代段 → DILA 朝代名（同段候选多个时优先本朝）
SEC_DYN = {
    "後漢": ["東漢"], "曹魏": ["曹魏"], "孫吳": ["孫吳"], "西晉": ["西晉"], "東晉": ["東晉"], "前涼": ["前涼"],
    "苻秦": ["前秦"], "姚秦": ["後秦"], "西秦": ["西秦"], "北涼": ["北涼"], "劉宋": ["劉宋"], "蕭齊": ["南齊"],
    "前梁": ["南梁", "西梁"], "後魏": ["北魏", "東魏", "西魏"], "高齊": ["北齊"], "周": ["北周"], "陳": ["陳"],
    "隋": ["隋"], "大唐": ["唐", "武周"], "大唐傳譯之餘": ["唐", "武周"],
}  # fmt: skip
# 夹注里写明朝代的（「符秦建元十二年」）按所写朝代取，不受本段断代限制
PREFIX = {
    "符秦": ["前秦"], "苻秦": ["前秦"], "姚秦": ["後秦"], "後秦": ["後秦"], "東晉": ["東晉"], "西晉": ["西晉"],
    "宋": ["劉宋"], "齊": ["南齊"], "梁": ["南梁"], "陳": ["陳"], "隋": ["隋"], "周": ["北周"],
    "魏": ["曹魏", "北魏", "東魏", "西魏"], "吳": ["孫吳"], "漢": ["東漢"], "唐": ["唐", "武周"],
}  # fmt: skip
_ALIAS = str.maketrans({"太": "泰", "泰": "太"})


def to_ad(eras: dict, era: str, n: int, gz: str | None, sec: str, pre: str | None) -> int | None:
    """年号 → 公元年；拿不准（无候选或多个不同年份）返回 None"""
    names = [era] + ([era.translate(_ALIAS)] if era.translate(_ALIAS) != era else [])
    cand = []
    for nm in names:
        for c in eras.get(nm, []):
            y = c["years"].get(n)
            if y is not None and (not gz or ganzhi(y) == gz):
                cand.append((y, c))
    # 同朝代同名年号常被库里按换帝拆成两段（義熙十四年＝418 与 419），同朝代取较早者
    best: dict = {}
    for y, c in cand:
        k = (tuple(c["dyn"]), c["rank"])
        if k not in best or y < best[k][0]:
            best[k] = (y, c)
    cand = list(best.values())
    if pre:
        cand = [x for x in cand if set(x[1]["dyn"]) & set(PREFIX[pre])]
    else:
        lo, hi = SPAN.get(sec, (-9999, 9999))
        cand = [x for x in cand if lo - 3 <= x[0] <= hi + 3]
        for keep in (
            lambda x: set(x[1]["dyn"]) & set(SEC_DYN.get(sec, [])),
            lambda x: x[1]["rank"] == 0,
        ):
            if len({y for y, _ in cand}) > 1 and any(keep(x) for x in cand):
                cand = [x for x in cand if keep(x)]
    ys = {y for y, _ in cand}
    return ys.pop() if len(ys) == 1 else None


def _clean(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).replace("\n", "")


_T = r"(?:[^<。]|<lb[^>]*/>|<anchor[^>]*/>|<pb[^>]*/>)"
_TOKEN = re.compile(
    r'<lb n="(\w+)" ed="T"/>(?:(?!<lb ).)*?<cb:jl_title>(.*?)</cb:jl_title><cb:jl_juan[^>]*>(.*?)</cb:jl_juan>'
    r'(<note place="inline">.*?</note>)?'
    r"|(?:<p[^>]*>|　)(右(?:<anchor[^>]*/>)*[一二三四五六七八九十百]" + _T + r"{0,60}?部(?:" + _T + r"{0,40}?卷)?)",
    re.S,
)
_WHO = re.compile(
    r"((?:[^\s，]{0,6}?(?:沙門|優婆塞|居士|清信士|婆羅門|王子|三藏|郡守|學士))[^\s，]{1,8}?)"
    r"(?:[，]|秦言|唐言|晉言|宋言|梁言|魏言|隋言|字|$)"
)


def extract(xml_path: str, eras: dict) -> list[dict]:
    x = Path(xml_path).read_text(encoding="utf8")
    era_re = re.compile(
        "(" + "|".join(PREFIX) + ")?(" + "|".join(sorted(eras, key=len, reverse=True)) + ")"
        "(元|[一二三四五六七八九十]{1,3})年(?:歲次|歲在|太歲)?([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])?"
    )
    juans = re.split(r'<cb:juan n="0*(\d+)" fun="open">', x)
    rows: list[dict] = []
    for k in range(1, len(juans), 2):
        jn = int(juans[k])
        if jn > 10:
            break
        for sec in re.split(r'<cb:div type="other"><cb:mulu level="3" type="其他">', juans[k + 1])[1:]:
            name = sec[: sec.find("<")]
            if name not in SPAN:  # 卷 10「敘列古今諸家目錄」是经录的目录，不是译经
                continue
            pending: list[dict] = []
            for tok in _TOKEN.finditer(sec):
                if tok.group(1) is None:
                    # 「右…部…卷。」之后第一句像人名的是译人；跳过「其本並在」「一百一十一卷」这类
                    after = _clean(re.sub(r"<note.*?</note>", "", sec[tok.end() : tok.end() + 600], flags=re.S))
                    who = ""
                    for sent in after.split("。")[1:6]:
                        sent = sent.strip()
                        if not sent or re.match(r"(其本|本在|見在|並|竝|此|上|已上|右|於中|[一二三四五六七八九十百]+卷)", sent):
                            continue
                        m = _WHO.match(sent)
                        who = m.group(1) if m else ""
                        break
                    for row in pending:
                        row["who"] = who
                    pending = []
                    continue
                note = _clean(tok.group(4) or "")
                row = {"juan": jn, "lb": tok.group(1), "sec": name, "who": "", "t": _clean(tok.group(2)),
                       "j": _clean(tok.group(3)), "y": None, "h": None, "note": note}  # fmt: skip
                e = era_re.search(note)
                if e:
                    row["h"] = e.group(0)
                    row["y"] = to_ad(eras, e.group(2), cn(e.group(3)), e.group(4), name, e.group(1))
                rows.append(row)
                pending.append(row)
    return rows


# ---------- 对藏内经典 ----------

# 开元录用的译名 → 通行名（佛津经典表的译者字段用通行名）
ALT = {
    "竺曇摩羅察": "竺法護", "安清": "安世高", "波羅末陀": "真諦", "拘羅那他": "真諦", "菩提留支": "菩提流支",
    "瞿曇般若流支": "般若流支", "阿儞真那": "寶思惟", "那連提黎耶舍": "那連提耶舍", "達摩笈多": "達磨笈多",
    "佛陀跋陀羅": "佛馱跋陀羅", "瞿曇僧伽提婆": "僧伽提婆",
}  # fmt: skip


def core_name(who: str) -> str:
    w = re.sub(r"^.*?(沙門|優婆塞|居士|清信士|婆羅門|王子|三藏|郡守|翻經學士|學士)", "", who)
    w = re.sub(r"^釋|等$|亦中印度人$|印度人也$|于闐國人$", "", w)
    return ALT.get(w, w)


def build(rows: list[dict], texts_tsv: str, kaiyuan_id: int) -> list[dict]:
    texts = collections.defaultdict(list)
    for line in Path(texts_tsv).read_text(encoding="utf8").splitlines():
        f = line.rstrip("\n").split("\t")
        if len(f) >= 4 and f[1] != KAIYUAN_CBETA:
            texts[f[2]].append((int(f[0]), f[3]))
    seen = set()
    out = []
    for r in rows:
        if not r["y"] or len(r["t"]) > 25 or re.search(r"今移|移在|移入|刪之|不錄|疑偽|偽經", r["note"]):
            continue
        if (r["t"], r["y"]) in seen:
            continue
        seen.add((r["t"], r["y"]))
        w = core_name(r["who"])
        raw = re.sub(r"^.*?(沙門|優婆塞|居士|清信士|婆羅門|王子|三藏|郡守|翻經學士|學士)|^釋", "", r["who"])
        names = {w, raw}
        hit = [
            tid
            for tid, tr in texts.get(r["t"], [])
            if any(n and (n in tr or (len(n) >= 3 and n[:3] in tr) or n[-2:] in tr) for n in names)
        ]
        item = {"y": r["y"], "t": r["t"], "j": r["j"], "w": w, "h": r["h"],
                "ju": r["juan"], "lh": r["lb"]}  # fmt: skip
        if hit:
            item["tid"] = hit[0]
        out.append(item)
    return sorted(out, key=lambda x: (x["y"], x["t"]))


def main() -> None:
    sql_path, xml_path, texts_tsv, out_path = sys.argv[1:5]
    kaiyuan_id = int(sys.argv[5]) if len(sys.argv) > 5 else 76
    eras = load_eras(sql_path)
    rows = extract(xml_path, eras)
    items = build(rows, texts_tsv, kaiyuan_id)
    with_era = sum(1 for r in rows if r["h"])
    print(f"{len(rows)} 部；夹注有年号 {with_era}；换算出公元年 {sum(1 for r in rows if r['y'])}；"
          f"去互见后 {len(items)}；对上藏内经典 {sum(1 for x in items if 'tid' in x)}")  # fmt: skip
    data = {
        "source": "《開元釋教錄》卷1–10 總括群經錄夾注；年號換算：DILA 時間規範資料庫（CC BY-SA 3.0）",
        "kaiyuan": kaiyuan_id,
        "items": items,
    }
    with open(out_path, "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


if __name__ == "__main__":
    main()
