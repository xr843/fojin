#!/usr/bin/env python3
"""逐块巡检：每个向量分块的文字是否出自它所标的那一卷。

为什么 check_embedding_juan_integrity.py 不够
--------------------------------------------
那个巡检只看每卷**最后一块**是否还在本卷（7 月的串卷形状：一卷的块一路越界到
后几卷），而且先按「嵌入字数 / 正文字数」做预筛。2026-10-26 生产回放发现另一种
形状：卷中间夹着整段别卷的文字、块数与字数都正常、末块也在本卷——预筛和末块判据
都放它过去。实例：《妙法蓮華經玄義》(text 7889) 567 块里 221 块的文字出自别卷，
第 10 卷第 19 块整块是第 8 卷的原文；RAG 的 ``[出处: 《X》第N卷]`` 取自这个
juan_num，模型照抄，答案的卷号就错了（近 30 天卷号准确率 92.6%，222 条错卷号里
87 条是这一类）。这些坏块全部创建于 2026-03/04 的旧入库，7 月之后重建的块无一出错。

判据
----
把块切成 16 字窗口：大半窗口落在本卷正文 → 本卷的块（只是换行/异文/边界差异）；
否则若窗口多数落在**同一部经的另一卷** → 错标块，记下它真正所属的卷。窗口在全经
都找不到的块不算错标（多为版本/异体字差异），不进修复清单。

用法（容器内，只读，全库约 40 分钟，可断点续跑）::

    python scripts/scan_embedding_juan_labels.py --out /data/juan-scan
    python scripts/scan_embedding_juan_labels.py --text-ids 7889,52 --out /tmp/x

输出 ``<out>/pairs.json``：``[[text_id, juan_num, 错标块数], ...]``，交给
``repair_stale_embeddings.py --pairs-file`` 重建。发现错标块数 ≥ --min-bad 的卷时
退出码 1。
"""

from __future__ import annotations

import argparse
import asyncio
import bisect
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text as sql_text

WINDOW = 16


class JuanIndex:
    """All of one text's juans in a single string, so "which juans contain this
    window" is one C-level ``str.find`` sweep instead of a scan per juan — the
    per-juan loop was quadratic in juan count and stalled on 600-juan texts."""

    def __init__(self, juans: dict[int, str]):
        self.juans = juans
        self._order = sorted(juans)
        self._starts: list[int] = []
        parts, pos = [], 0
        for j in self._order:
            self._starts.append(pos)
            parts.append(juans[j])
            pos += len(juans[j]) + 1
        self._all = "\x00".join(parts)  # separator: a window never spans two juans

    def juans_containing(self, window: str) -> set[int]:
        found, at = set(), self._all.find(window)
        while at != -1:
            found.add(self._order[bisect.bisect_right(self._starts, at) - 1])
            at = self._all.find(window, at + 1)
        return found


def classify_chunk(chunk: str, label: int, index: JuanIndex | dict[int, str]) -> int | None:
    """Return the juan a mislabelled chunk really belongs to, or None if it is fine.

    ``chunk`` and every juan body must already be normalised the same way.
    None covers both "belongs to its own juan" and "can't place it anywhere" —
    only a chunk that demonstrably lives in a *different* juan of the same text
    is a mislabel worth re-embedding.
    """
    if not isinstance(index, JuanIndex):
        index = JuanIndex(index)
    own = index.juans.get(label)
    if own is None or len(chunk) < WINDOW * 2 or chunk in own:
        return None
    wins = [chunk[k : k + WINDOW] for k in range(0, len(chunk) - WINDOW, WINDOW)]
    if sum(w in own for w in wins) >= len(wins) * 0.5:
        return None
    home = Counter(j for w in wins for j in index.juans_containing(w) if j != label)
    if not home:
        return None
    j, hits = home.most_common(1)[0]
    return j if hits >= len(wins) * 0.5 else None


async def _scan_text(session, text_id: int, normalise) -> Counter:
    """{juan_num: mislabelled chunk count} for one text."""
    contents = (
        await session.execute(
            sql_text("SELECT juan_num, content FROM text_contents WHERE text_id = :t"),
            {"t": text_id},
        )
    ).all()
    rows = (
        await session.execute(
            sql_text("SELECT juan_num, chunk_text FROM text_embeddings WHERE text_id = :t"),
            {"t": text_id},
        )
    ).all()
    # End the read transaction before any CPU work: prod kills a session idle in a
    # transaction for 60s, and normalising + classifying the largest texts takes
    # longer than that — the first two full runs both died on text #4,815.
    await session.rollback()
    bad: Counter = Counter()
    juans = {j: normalise(c or "") for j, c in contents}
    if not juans:
        return bad
    index = JuanIndex(juans)
    for j, chunk in rows:
        if classify_chunk(normalise(chunk or ""), j, index) is not None:
            bad[j] += 1
    return bad


async def main() -> int:
    from app.database import async_session
    from app.services.quote_verifier import normalise_for_match

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="directory for pairs.json and the resume log")
    ap.add_argument("--text-ids", default="", help="comma-separated text ids (default: all embedded texts)")
    ap.add_argument(
        "--min-bad", type=int, default=3, help="juans with at least this many mislabelled chunks go into pairs.json"
    )
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    done_path, found_path = f"{args.out}/done.txt", f"{args.out}/found.jsonl"
    done: set[str] = set()
    if os.path.exists(done_path):
        with open(done_path) as f:
            done = set(f.read().split())
    async with async_session() as s:
        if args.text_ids:
            tids = [int(x) for x in args.text_ids.split(",") if x.strip()]
        else:
            tids = [
                r[0]
                for r in (await s.execute(sql_text("SELECT DISTINCT text_id FROM text_embeddings ORDER BY 1"))).all()
            ]

    t0 = time.time()
    for i, tid in enumerate(tids):
        if str(tid) in done:
            continue
        async with async_session() as s:  # one short session per text: never hold a snapshot for 40 minutes
            bad = await _scan_text(s, tid, normalise_for_match)
        if bad:
            with open(found_path, "a") as f:
                f.write(json.dumps({"text_id": tid, "bad": dict(bad)}) + "\n")
        with open(done_path, "a") as f:
            f.write(f"{tid}\n")
        if i % 500 == 0:
            print(f"{i}/{len(tids)} texts, {time.time() - t0:.0f}s", flush=True)

    pairs: dict[tuple[int, int], int] = {}
    if os.path.exists(found_path):
        with open(found_path) as f:
            for line in f:
                r = json.loads(line)
                for j, n in r["bad"].items():
                    pairs[(r["text_id"], int(j))] = n  # last write wins on a resumed run
    keep = sorted([t, j, n] for (t, j), n in pairs.items() if n >= args.min_bad)
    with open(f"{args.out}/pairs.json", "w") as f:
        json.dump(keep, f)
    print(
        f"DONE: {len(keep)} juans across {len({t for t, _, _ in keep})} texts with >= {args.min_bad} "
        f"mislabelled chunks ({sum(n for _, _, n in keep)} chunks) -> {args.out}/pairs.json",
        flush=True,
    )
    return 1 if keep else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
