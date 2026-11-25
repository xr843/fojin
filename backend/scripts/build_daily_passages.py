"""生成「每日一段」段落池：frontend/src/data/dailyPassages.json。

每条候选（daily_passages_candidates.txt，一行一段，繁体按 CBETA 字形）都送生产
/api/verify/claim 全藏逐字核对：只收「整段一次命中、相似度 1.0、非弱匹配」的，出处
（经名、卷、阅读器行号链接）从核对结果里取，不靠人记忆写出处。核不到的打印出来、不收。

出处怎么选：核对结果按大藏经编号排，第一条常是后人引用它的注疏/语录（如「淨極光通達」
落在《楞嚴經勢至圓通章疏鈔》）——说「出自注疏」会误导读者。所以：
- 行尾写了 `|T0374` 的，必须在那部经里逐字命中才收，出处就用它（公认原出某经时用）；
- 没写的，取第一条经部或论部（canon_class 为 sutra / treatise）的出处，没有就不收。

顺序按经打散（轮流取各部经），相邻两天不落在同一部经。

用法（只用标准库；接口有限流，每条间隔 6 秒）：
    python backend/scripts/build_daily_passages.py
"""

import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from collections import OrderedDict

ROOT = pathlib.Path(__file__).resolve().parents[2]
CANDIDATES = ROOT / "backend/scripts/daily_passages_candidates.txt"
OUT = ROOT / "frontend/src/data/dailyPassages.json"
API = "https://fojin.app/api/verify/claim?q="


PRIMARY_CLASSES = {"sutra", "treatise"}
SENTENCE_END = "。？！"


def verify(q: str, hint: str | None = None) -> dict | None:
    for _ in range(3):
        try:
            req = urllib.request.Request(API + urllib.parse.quote(q), headers={"User-Agent": "fojin-daily-build"})
            d = json.load(urllib.request.urlopen(req, timeout=60))
            break
        except Exception as exc:  # 网络抖动重试
            print("  retry:", exc, file=sys.stderr)
            time.sleep(15)
    else:
        return None
    segs = d.get("segments") or []
    if len(segs) != 1:
        return None
    s = segs[0]
    if not s.get("found") or (s.get("similarity") or 0) < 0.999 or s.get("weak") or not s.get("sources"):
        return None
    if hint:
        src = next((x for x in s["sources"] if x["cbeta_id"] == hint), None)
    else:
        src = next((x for x in s["sources"] if x.get("canon_class") in PRIMARY_CLASSES), None)
    if src is None:
        return None
    url = urllib.parse.urlsplit(src["reader_url"])
    return {
        "text": q,
        "title_zh": src["title_zh"],
        "cbeta_id": src["cbeta_id"],
        "text_id": src["text_id"],
        "juan_num": src["juan_num"],
        "reader_path": url.path + ("?" + url.query if url.query else ""),
    }


def interleave(rows: list[dict]) -> list[dict]:
    groups: OrderedDict[str, list[dict]] = OrderedDict()
    for r in rows:
        groups.setdefault(r["cbeta_id"], []).append(r)
    queues = sorted(groups.values(), key=len, reverse=True)
    out: list[dict] = []
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    return out


def main() -> None:
    kept, dropped = [], []
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        q, _, hint = line.partition("|")
        if q[-1] not in SENTENCE_END:  # 每句必须是完整的自然句，以句末标点收尾
            dropped.append(q)
            print("--  （缺句末标点）" + q, flush=True)
            continue
        r = verify(q, hint or None)
        (kept if r else dropped).append(r or q)
        print(("OK  " if r else "--  ") + q, flush=True)
        time.sleep(6)
    rows = interleave(kept)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("⚠️ 接着在 frontend/ 下跑 node scripts/daily-hans.mjs 补简体字段（首页用）", flush=True)
    print(f"\n收 {len(rows)} 段，丢 {len(dropped)} 段 → {OUT}")
    for q in dropped:
        print("  未收：", q)


if __name__ == "__main__":
    main()
