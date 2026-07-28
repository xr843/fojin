#!/usr/bin/env python3
"""巡检「声称有内容」的标志与实际数据是否一致。

为什么需要这个脚本
------------------
2026-07-28 线上发现：从 /chat 点开《阿毘達磨俱舍論》第16卷的引文，抽屉里
只有一行「… 前文（本卷第 0 段之前）」，正文一片空白。根因是后端把
``has_more_before`` 写成了一行算术（``low > 0``）而非查库，于是在被引 chunk
根本不存在时仍宣称「前面还有内容」。

那个具体缺陷已修，但它暴露的是一整类风险：**UI 依据某个标志给出「打开原文」
的入口，而那个标志与实际数据可能脱节。** 全站这类入口至少有三处：

    SemanticCard.tsx        hit.has_content && (…)
    TextDetailPage.tsx      text.has_content && (…)
    sources/SourceCard.tsx  s.has_local_fulltext && (…)

而 ``buddhist_texts.has_content`` 只在导入脚本里被置为 true
（import_content.py / import_suttacentral.py / import_sc_offline.py），
**代码里没有任何地方把它置回 false，也没有任何一致性校验**。内容一旦被
删除、重导入失败、或分块流程中断，标志就会留在 true 上，UI 继续把读者
送去空白页面——而且全程不报错。

这类失效的共同特征是「不崩溃」：接口 200、前端无异常、日志干净，只有
读者看到一片空白。因此必须主动去量，不能等报错。

用法
----
    python scripts/check_content_flags.py            # 只报告
    python scripts/check_content_flags.py --fix      # 顺带把假 true 置回 false

退出码：0 = 一致；1 = 发现不一致（可用于 CI / 定时任务告警）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# 声称有正文、却查不到任何 text_contents 行
_ORPHAN_CONTENT = """
SELECT bt.id, bt.cbeta_id, COALESCE(bt.title_zh, '')
FROM buddhist_texts bt
WHERE bt.has_content = true
  AND NOT EXISTS (SELECT 1 FROM text_contents tc WHERE tc.text_id = bt.id)
ORDER BY bt.id
"""

# 声称有正文、也确有正文，却没有任何向量分块 —— 引文抽屉正是查 text_embeddings，
# 所以这一类会精确复现「引文点开是空白」的症状
_ORPHAN_EMBEDDING = """
SELECT bt.id, bt.cbeta_id, COALESCE(bt.title_zh, '')
FROM buddhist_texts bt
WHERE bt.has_content = true
  AND EXISTS (SELECT 1 FROM text_contents tc WHERE tc.text_id = bt.id)
  AND NOT EXISTS (SELECT 1 FROM text_embeddings te WHERE te.text_id = bt.id)
ORDER BY bt.id
"""

# 反向：有正文却标志为 false —— 危害较小（只是入口被藏起来），但同样是脱节
_UNDERCLAIMED = """
SELECT bt.id, bt.cbeta_id, COALESCE(bt.title_zh, '')
FROM buddhist_texts bt
WHERE bt.has_content = false
  AND EXISTS (SELECT 1 FROM text_contents tc WHERE tc.text_id = bt.id)
ORDER BY bt.id
"""

_FIX = """
UPDATE buddhist_texts SET has_content = false
WHERE has_content = true
  AND NOT EXISTS (SELECT 1 FROM text_contents tc WHERE tc.text_id = buddhist_texts.id)
"""


def _fmt(rows: list, limit: int = 15) -> str:
    out = [f"    #{r[0]:<7} {r[1] or '':<16} {r[2][:28]}" for r in rows[:limit]]
    if len(rows) > limit:
        out.append(f"    …… 另有 {len(rows) - limit} 条")
    return "\n".join(out)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fix", action="store_true", help="把查无正文的 has_content 置回 false")
    ap.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="数据库连接串")
    args = ap.parse_args()

    if not args.dsn:
        print("需要 --dsn 或环境变量 DATABASE_URL", file=sys.stderr)
        return 2

    engine = create_async_engine(args.dsn)
    bad = 0
    async with engine.connect() as conn:
        total = (await conn.execute(text("SELECT count(*) FROM buddhist_texts"))).scalar_one()
        claimed = (
            await conn.execute(text("SELECT count(*) FROM buddhist_texts WHERE has_content = true"))
        ).scalar_one()
        print(f"buddhist_texts 共 {total} 条，其中 has_content = true 的 {claimed} 条\n")

        for title, sql, why in (
            ("① 声称有正文、实则无正文", _ORPHAN_CONTENT,
             "UI 会给出「打开原文」入口，点进去是空白"),
            ("② 有正文、但无向量分块", _ORPHAN_EMBEDDING,
             "引文抽屉查的正是 text_embeddings —— 这一类会精确复现「引文点开是空白」"),
            ("③ 有正文、标志却为 false", _UNDERCLAIMED,
             "危害较小：入口被藏起来，读者以为没有"),
        ):
            rows = (await conn.execute(text(sql))).fetchall()
            mark = "✅" if not rows else "⚠️"
            print(f"{mark} {title}：{len(rows)} 条    （{why}）")
            if rows:
                print(_fmt(rows))
                if title.startswith("①") or title.startswith("②"):
                    bad += len(rows)
            print()

        if args.fix and bad:
            async with engine.begin() as wconn:
                res = await wconn.execute(text(_FIX))
                print(f"已把 {res.rowcount} 条查无正文的 has_content 置回 false")

    await engine.dispose()
    if bad:
        print(f"发现 {bad} 条「标志声称有内容、实际没有」——这些正是读者会点进空白页的入口。")
        return 1
    print("一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
