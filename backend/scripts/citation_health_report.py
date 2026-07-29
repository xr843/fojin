#!/usr/bin/env python3
"""回放最近已服务的答案，报告引用健康度三项指标。

为什么是回放，不是 eval
----------------------
`eval/run_eval.py` 能算 `fascicle_accuracy_rate`，但夜间回归门跑的是 `--no-llm`
——它在生成答案前就返回了，所以**忠实度指标在定时任务里从不被计算**。带 LLM 的
全量 eval 要烧 75 次生成 + 75 次评判，且题库是固定的 90 题。

回放已经服务出去的答案没有这些问题：成本为零，样本是真实用户提问，而且随时间
持续积累。2026-07-29 首测就拿到 1,672 条可判定引用，比一次 eval 多 6–8 倍。

报告什么
--------
1. **卷号准确率** —— 带引号的引文，是否真的在所标的那一卷里。
   拿 ``text_contents`` 做独立真源，绕开召回的 chunk：护栏会跨卷回退，
   结构性看不见「引错卷」（详见 eval/faithfulness.compute_fascicle_accuracy）。

2. **引号覆盖率** —— 多少引用带「」或引用块。没有引号的引用，quote_verifier
   查不了、引文抽屉锚不了、卷号准确率也量不到它——它完全游离在核验体系之外。
   2026-07-29 实测这一类占 51.6%，是当前最大的盲区。

3. **引文定位与所标卷号的一致率** —— 引文能在该经的哪一卷逐字找到，那一卷与
   答案所标的卷号是否相同。
   这一项是为一个**尚未裁决的问题**攒证据：能否让运行时护栏按引文所在位置自动
   纠正卷号。此前实测该做法 18 错 2 对而被否决，但那次用的是索引修复前的答案，
   18 处误改全部由错标 chunk 驱动。索引现已干净（受损面归零），结论可能不同。
   若这一项长期高位，自动纠正就是可行的；若不然，就该老实走提示词那条路。

刻意不设阈值
-----------
修复前基线 0.722，修复后样本只有 25 条引文——数据不足时定红线，要么天天误报、
要么永不触发。先纯报告积累两周，阈值连同 cron 的告警一起补。所以本脚本**总是
退出 0**，除非自身出错。

用法（在 fojin-backend 容器内，cwd /app）：
    python scripts/citation_health_report.py
    python scripts/citation_health_report.py --days 7 --limit 2000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.services.citation_guard import _norm_title
from app.services.quote_verifier import (
    _BLOCKQUOTE_CITATION_RE,
    _QUOTE_CITATION_RE,
    iter_quote_citations,
    normalise_for_match,
)

# 所有 【《经名》第N卷】 引用，无论前面有没有引号 —— 引号覆盖率的分母。
_ANY_CITATION_RE = re.compile(r"【《(?P<title>[^》]+)》(?:第(?P<juan>\d+)卷)?】")

_ANSWERS = sql_text(
    """
    -- CAST 而非 ::text —— SQLAlchemy 的 text() 会把 `::text` 里的冒号当成
    -- 绑定参数名，语句直接送不到数据库；CAST 两种方言都认，测试也才跑得起来。
    SELECT id, content, CAST(sources AS TEXT)
    FROM chat_messages
    WHERE role = 'assistant'
      AND content LIKE '%【《%'
      AND sources IS NOT NULL
      AND created_at > :since
    ORDER BY id DESC
    LIMIT :limit
    """
)


def _title_index(raw_sources: str) -> dict[str, int]:
    """{繁简折叠后的经名 -> text_id}，与护栏的解析规则同源。"""
    try:
        payload = json.loads(raw_sources)
    except (TypeError, ValueError):
        return {}
    items = payload if isinstance(payload, list) else payload.get("sources") or []
    out: dict[str, int] = {}
    for s in items:
        if s.get("title_zh") and (s.get("text_id") or 0) > 0:
            out.setdefault(_norm_title(s["title_zh"]), s["text_id"])
    return out


class _Corpus:
    """按 (text_id, juan) 和 text_id 缓存归一化后的正文，全程只读。"""

    def __init__(self, conn):
        self._conn = conn
        self._juan: dict[tuple[int, int], str | None] = {}
        self._whole: dict[int, list[tuple[int, str]]] = {}

    async def juan(self, text_id: int, juan_num: int) -> str | None:
        key = (text_id, juan_num)
        if key not in self._juan:
            row = (
                await self._conn.execute(
                    sql_text(
                        "SELECT content FROM text_contents "
                        "WHERE text_id = :t AND juan_num = :j AND lang = 'lzh' LIMIT 1"
                    ),
                    {"t": text_id, "j": juan_num},
                )
            ).fetchone()
            self._juan[key] = normalise_for_match(row[0]) if row else None
        return self._juan[key]

    async def juans_of(self, text_id: int) -> list[tuple[int, str]]:
        if text_id not in self._whole:
            rows = (
                await self._conn.execute(
                    sql_text(
                        "SELECT juan_num, content FROM text_contents "
                        "WHERE text_id = :t AND lang = 'lzh' ORDER BY juan_num"
                    ),
                    {"t": text_id},
                )
            ).fetchall()
            self._whole[text_id] = [(r[0], normalise_for_match(r[1])) for r in rows]
        return self._whole[text_id]


async def _report(conn, days: int, limit: int) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (await conn.execute(_ANSWERS, {"since": since, "limit": limit})).fetchall()
    corpus = _Corpus(conn)

    citations = anchored = 0            # 引号覆盖率
    fascicle_checked = fascicle_ok = 0  # 卷号准确率
    located = located_agrees = 0        # 引文定位 vs 所标卷号

    for _id, content, raw_sources in rows:
        by_title = _title_index(raw_sources)
        if not by_title:
            continue

        # 引号覆盖率：带引号的引用位置（含引用块）对全部引用取比。
        anchored_ends = {m.end() for m in _QUOTE_CITATION_RE.finditer(content)}
        anchored_ends |= {m.end() for m in _BLOCKQUOTE_CITATION_RE.finditer(content)}
        for m in _ANY_CITATION_RE.finditer(content):
            if not m.group("juan"):
                continue
            if _norm_title(m.group("title")) not in by_title:
                continue
            citations += 1
            if m.end() in anchored_ends:
                anchored += 1

        for cite in iter_quote_citations(content):
            if cite.juan is None:
                continue
            text_id = by_title.get(_norm_title(cite.title))
            if text_id is None:
                continue
            body = await corpus.juan(text_id, cite.juan)
            if body is None:
                # 查不到该卷正文 —— 判不了就不判，绝不静默记错。
                continue
            needle = normalise_for_match(cite.quote)
            fascicle_checked += 1
            if needle in body:
                fascicle_ok += 1
                located += 1
                located_agrees += 1
                continue
            # 所标卷没有 —— 看看它到底在哪一卷。命中多卷时取最小，与
            # citation_guard._juan_holding_quote 的决胜规则保持一致。
            holders = [j for j, text in await corpus.juans_of(text_id) if needle in text]
            if holders:
                located += 1
                if min(holders) == cite.juan:
                    located_agrees += 1

    return {
        "answers": len(rows),
        "days": days,
        "citations": citations,
        "anchored": anchored,
        "fascicle_checked": fascicle_checked,
        "fascicle_ok": fascicle_ok,
        "located": located,
        "located_agrees": located_agrees,
    }


def _pct(num: int, den: int) -> str:
    return f"{num / den * 100:5.1f}%  ({num}/{den})" if den else "     —  (0/0)"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7, help="回放最近几天的答案")
    ap.add_argument("--limit", type=int, default=2000, help="最多回放多少条答案")
    ap.add_argument("--json", action="store_true", help="输出 JSON，便于入库/画图")
    args = ap.parse_args()

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            r = await _report(conn, args.days, args.limit)
    finally:
        await engine.dispose()

    if args.json:
        print(json.dumps(r, ensure_ascii=False))
        return 0

    print(f"引用健康度 · 最近 {r['days']} 天 · {r['answers']} 条含引用答案\n")
    print(f"  卷号准确率        {_pct(r['fascicle_ok'], r['fascicle_checked'])}")
    print("     带引号的引文，是否真的在所标的那一卷里（真源：text_contents）")
    print()
    print(f"  引号覆盖率        {_pct(r['anchored'], r['citations'])}")
    print("     无引号的引用完全游离在核验体系之外：查不了、锚不了、也量不到")
    print()
    print(f"  定位与标注一致率  {_pct(r['located_agrees'], r['located'])}")
    print("     引文能逐字定位的前提下，它所在的卷是否就是答案标的那一卷。")
    print("     长期高位 → 运行时按引文自动纠正卷号可行；反之应走提示词约束。")
    print()
    print("  * 刻意不设阈值：修复后样本尚不足以定红线，先积累两周。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
