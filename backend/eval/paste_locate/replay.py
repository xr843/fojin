"""贴原文定位：生产回放评测（判据见同目录 GATE.md）。

在后端容器内运行，读生产库的真实用户消息——**明细含用户原话，只写到容器 /tmp，
不要提交进仓库**；仓库里只放本脚本与汇总数字。

    docker exec -e PYTHONPATH=/app -w /app fojin-backend \
        python -u /tmp/replay.py --days 90 --out /tmp/paste_eval.jsonl

真值（与被测定位器独立）：对每条消息，先逐句在全藏做短语检索，得到「原文里存在」的
小句；再在相邻的存在小句里，由长到短找能整体按句命中的最长窗口（ES phrase，所有
句都命中）。≥2 句且 ≥12 个汉字，或单句 ≥12 个汉字，即判为「贴了原文」。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

from sqlalchemy import text as sql_text

from app.core.elasticsearch import init_es
from app.database import async_session

try:
    from app.services.passage_locator import han_count, inject_located, locate_pasted_passage, split_clauses
except ImportError:  # 上线前评测：模块还没部署进镜像，从 /tmp 旁路导入
    from passage_locator import han_count, inject_located, locate_pasted_passage, split_clauses
from app.services.quote_verifier import normalise_for_match as norm

MAX_CONTEXT = 5
TITLE_RE = re.compile(r"《([^》]{1,40})》")


async def _phrase_hit(es, clauses: list[str]) -> bool:
    body = {
        "query": {"bool": {
            "must": [{"match_phrase": {"content": {"query": c, "analyzer": "cjk_content"}}} for c in clauses],
            "filter": [{"term": {"lang": "lzh"}}],
        }},
        "size": 0,
        "terminate_after": 1,
    }
    r = await es.search(index="text_contents", body=body, timeout="10s")
    return r["hits"]["total"]["value"] > 0


async def _contiguous_in_canon(es, db, window: list[str]) -> bool:
    """ES 的 must 只保证这几句「出现在同一卷」，不保证相邻。真值定义是「连续窗口」，
    所以再到 text_contents 整卷原文里确认它是一段连续文字（v1 漏了这一步，把散落在
    民国现代汉语著作里的闲聊句子也判成了「贴了原文」）。"""
    body = {
        "query": {"bool": {
            "must": [{"match_phrase": {"content": {"query": c, "analyzer": "cjk_content"}}} for c in window],
            "filter": [{"term": {"lang": "lzh"}}],
        }},
        "size": 5,
        "_source": ["text_id", "juan_num"],
    }
    hits = (await es.search(index="text_contents", body=body))["hits"]["hits"]
    needle = "".join(norm(c) for c in window)
    for h in hits:
        src = h.get("_source") or {}
        row = (await db.execute(
            sql_text("SELECT content FROM text_contents WHERE text_id = :t AND juan_num = :j"),
            {"t": src.get("text_id"), "j": src.get("juan_num")},
        )).first()
        if row and needle in norm(row[0] or ""):
            return True
    return False


async def ground_truth(es, message: str) -> str | None:
    async def _confirm(es, win):
        async with async_session() as db:
            return await _contiguous_in_canon(es, db, win)

    clauses = split_clauses(message)
    if han_count("".join(clauses)) < 12:
        return None
    exists = [han_count(c) >= 2 and await _phrase_hit(es, [c]) for c in clauses]
    runs: list[list[int]] = []
    cur: list[int] = []
    for i, ok in enumerate(exists):
        if ok:
            cur.append(i)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    best: list[str] | None = None
    for run in runs:
        for width in range(len(run), 0, -1):
            found = None
            for st in range(0, len(run) - width + 1):
                win = [clauses[k] for k in run[st:st + width]]
                if han_count("".join(win)) < 12:
                    continue
                if (width == 1 or await _phrase_hit(es, win)) and await _confirm(es, win):
                    found = win
                    break
            if found:
                if best is None or han_count("".join(found)) > han_count("".join(best)):
                    best = found
                break
    return None if best is None else "".join(norm(c) for c in best)


def contains(chunk_text: str, gt: str) -> bool:
    return gt in norm(chunk_text or "")


async def main(days: int, out_path: str, limit: int | None, ids_file: str | None = None, no_gt: bool = False) -> None:
    es = await init_es()
    async with async_session() as db:
        rows = (await db.execute(sql_text(f"""
            SELECT u.id, u.content,
              (SELECT a.sources FROM chat_messages a
                WHERE a.session_id = u.session_id AND a.role = 'assistant' AND a.id > u.id
                ORDER BY a.id LIMIT 1)
            FROM chat_messages u
            WHERE u.role = 'user' AND u.created_at > now() - interval '{int(days)} days'
            ORDER BY u.id"""))).all()
    if ids_file:
        with open(ids_file, encoding="utf-8") as f:
            keep = {int(x) for x in f.read().split()}
        rows = [r for r in rows if r[0] in keep]
    if limit:
        rows = rows[:limit]
    with open(out_path, "w", encoding="utf-8") as out:
        for mid, content, sources in rows:
            content = content or ""
            sources = sources or []
            gt = None if no_gt else await ground_truth(es, content)
            t0 = time.monotonic()
            async with async_session() as db:
                located = await locate_pasted_passage(es, db, content)
            ms = round((time.monotonic() - t0) * 1000)
            rec = {"id": mid, "gt": gt is not None, "locate_ms": ms, "fired": located is not None}
            if gt is not None:
                old = [s for s in sources if isinstance(s, dict)]
                rec["old_hit"] = any(contains(s.get("chunk_text"), gt) for s in old)
                if located is not None:
                    new = inject_located(located.chunk, old, MAX_CONTEXT)
                else:
                    new = old[:MAX_CONTEXT]
                rec["new_hit"] = any(contains(s.get("chunk_text"), gt) for s in new)
                rec["located_contains_gt"] = located is not None and contains(located.chunk["chunk_text"], gt)
            if located is not None:
                rec["located"] = {
                    "cbeta_id": located.chunk.get("cbeta_id"), "title": located.chunk.get("title_zh"),
                    "juan": located.chunk["juan_num"], "chunk": located.chunk["chunk_index"],
                    "window_han": located.window_han, "texts_with_window": located.texts_with_window,
                    # G2 复核：注入块必须真的包含用户消息里的这段窗口
                    "window_in_chunk": norm(located.window_text) in norm(located.chunk["chunk_text"]),
                }
                rec["named_titles"] = TITLE_RE.findall(content)
                # 明细（只在容器/本机临时目录里，用于人工复核）
                rec["msg_head"] = content[:160]
                rec["window"] = located.window_text[:80]
            elif gt is not None:
                rec["msg_head"] = content[:160]
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
    await es.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--out", default="/tmp/paste_eval.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", default=None, help="只回放这些消息 id（空白分隔的文件）")
    ap.add_argument("--no-gt", action="store_true", help="只跑定位器，不算真值（用于复核误注入）")
    a = ap.parse_args()
    asyncio.run(main(a.days, a.out, a.limit, a.ids, a.no_gt))
