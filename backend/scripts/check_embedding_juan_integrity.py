#!/usr/bin/env python3
"""巡检向量分块是否真的落在它所标的那一卷里。

为什么需要这个脚本
------------------
2026-07-29 用户反馈：问「纯白业是否都包含身语业」，答案引了一段逐字正确的
《俱舍論》原文，却标成第13卷——该段实出卷十六。根因是 ``text_embeddings``
的 ``juan_num`` 串卷：旧管线把多卷正文当作一卷切块，每一块都盖上**第一卷**
的卷号。text 38 的 juan_num=13 存了 109 个 chunk，实际覆盖真实卷 13→17。
``rag_retrieval`` 的 ``[出处: 《X》第N卷]`` 表头取自这个 juan_num，模型忠实
照抄。全库当时有 999 卷 / 550 部处于这个状态。

这类缺陷有三个特征，合起来使它极难被发现：

1. **不崩溃。** 接口 200、日志干净、答案通顺，只有卷号是错的。
2. **护栏帮着掩盖。** citation_guard 的白名单就是从这些错卷号建的，
   quote_verifier 在那个 chunk 里确实逐字找得到引文——两道防线都发绿灯。
3. **评测看不见。** eval 的黄金来源 90 题里只有 8 题标了卷号，其余按经名
   匹配、卷号=任意，所以回归门对「引错卷」完全免疫。

修复脚本（repair_stale_embeddings.py）也曾看不见它：那里原本只找「嵌入过少」
的卷（``e < 0.9c``），而本缺陷是「嵌入过多」，谓词恒假，于是被跳过了很久。

所以必须有一条**不依赖金标、不依赖模型、不依赖有人报告**的客观不变式：
**一卷的分块，必须出自这一卷的正文。** 违反即数据损坏。

判据
----
取每卷 chunk_index 最大的那一块（分块是顺序的，最远的一块若仍在卷内，
则没有任何一块越界），检查其正文是否为该卷 ``text_contents.content``
的子串。倍数（嵌入字数/正文字数）只作预筛——它会误报：切得更密但并未
越界的卷同样是高倍数，重嵌它们会打乱 chunk_index、作废本来完好的
alignment 引用。实测纯倍数判据在生产多选出 882 卷。

用法
----
    python scripts/check_embedding_juan_integrity.py           # 只报告
    python scripts/check_embedding_juan_integrity.py --limit 40

退出码：0 = 全部分块都在本卷内；1 = 发现越界（可用于 CI / 定时任务告警）。
修复用 ``scripts/repair_stale_embeddings.py``（它按同一判据选取候选）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.repair_stale_embeddings import _find_candidates

# 判据不在这里重写，而是直接复用修复脚本的候选查询。
#
# 两边各写一套 SQL 是这类工具最容易出的问题：门禁报的和修复脚本修的会悄悄
# 变成两批。一旦漂移，要么门禁天天报一批修不掉的，要么修复脚本改了判据而
# 门禁还在用旧的、继续放行新形态的损坏。共用同一个函数，这种漂移不可能发生。
#
# ``ratio=0`` 关掉「嵌入过少」那一侧（``e < 0`` 恒假）：那一侧代表正文被截断，
# 与本不变式（分块必须出自本卷）是两回事，混在一起报会让告警失去指向性。
_UNDER_SIDE_OFF = 0.0
_OVER_RATIO = 1.3
_MIN_CONTENT = 500


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=15, help="最多列出多少卷")
    ap.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="数据库连接串")
    args = ap.parse_args()
    if not args.dsn:
        print("需要 --dsn 或环境变量 DATABASE_URL", file=sys.stderr)
        return 2

    engine = create_async_engine(args.dsn)
    try:
        async with engine.connect() as conn:
            rows = await _find_candidates(
                conn, _UNDER_SIDE_OFF, _MIN_CONTENT, _OVER_RATIO
            )
    finally:
        await engine.dispose()

    if not rows:
        print("✓ 向量分块与卷号一致：没有任何一卷的分块越界到别卷")
        return 0

    texts = len({t for t, _, _, _ in rows})
    print(f"✗ {len(rows)} 卷 / {texts} 部经的分块越界到了别的卷：")
    for tid, juan, content_chars, embedded in sorted(
        rows, key=lambda r: r[3] / max(r[2], 1), reverse=True
    )[: args.limit]:
        print(
            f"    text {tid:<6} 第{juan}卷   嵌入 {embedded} 字 / 正文 "
            f"{content_chars} 字  ({embedded / max(content_chars, 1):.1f}×)"
        )
    if len(rows) > args.limit:
        print(f"    … 另有 {len(rows) - args.limit} 卷")
    print(
        "\n这些卷的 RAG 命中会带着错误的 `[出处: 《X》第N卷]` 表头进入提示词，"
        "\n答案里的卷号随之出错，而两道护栏都会放行（白名单本身就是从错卷号建的）。"
        "\n修复：python scripts/repair_stale_embeddings.py --dry-run  然后去掉 --dry-run",
    )
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
