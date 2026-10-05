"""贴原文定位 G5：同一问题、同一模型配置，旧管线 vs 新管线各答一次。

两臂用同一份新版检索代码（旁路加载见 attribution.py），旧臂只关 ENABLE_PASTE_LOCATE，
所以唯一差别是定位器（含上下文标注）。输入是 replay.py 的输出（取 gt=true 的随机 n 条）。
**明细含用户原话与答案，只写容器 /tmp，不提交**。

    docker exec -e PYTHONPATH=/tmp:/app -w /app fojin-backend \
        python -u /tmp/answers.py --replay /tmp/paste_eval_v2.jsonl --n 30 --out /tmp/paste_answers.jsonl

生成参数照抄 eval/run_eval.py（build_eval_llm_body、temperature 0），两臂答案跑同一套确定性忠实度。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random

import httpx
from attribution import R, _answer, ensure_locator_alive
from eval.faithfulness import compute_faithfulness, compute_fascicle_accuracy
from eval.run_eval import EVAL_LLM_TIMEOUT_S, _prefetch_cited_fascicles
from sqlalchemy import text as sql_text

from app.database import async_session


async def _faith(answer: str, sources) -> dict:
    if answer.startswith("[ERROR]"):
        return {}
    f = compute_faithfulness(answer, sources)
    async with async_session() as s:
        juan_text = await _prefetch_cited_fascicles(s, answer, sources)
    f.update(compute_fascicle_accuracy(answer, juan_text))
    return f


async def one(client, sem, mid: int, question: str) -> dict:
    async with sem:
        R.ENABLE_PASTE_LOCATE = False
        async with async_session() as s:
            old_src, old_ctx = await R.retrieve_rag_context(s, question)
        R.ENABLE_PASTE_LOCATE = True
        async with async_session() as s:
            new_src, new_ctx = await R.retrieve_rag_context(s, question)
        old_ans, new_ans = await asyncio.gather(_answer(client, old_ctx, question), _answer(client, new_ctx, question))
        return {
            "id": mid,
            "question": question,
            "context_changed": "[用户原文定位]" in new_ctx,
            "located_title": new_src[0].title_zh if new_src and "[用户原文定位]" in new_ctx else None,
            "located_text": new_src[0].chunk_text if new_src and "[用户原文定位]" in new_ctx else None,
            "old": {"answer": old_ans, "faith": await _faith(old_ans, old_src), "titles": [x.title_zh for x in old_src]},
            "new": {"answer": new_ans, "faith": await _faith(new_ans, new_src), "titles": [x.title_zh for x in new_src]},
        }


async def main(replay: str, n: int, out: str, seed: int) -> None:
    with open(replay, encoding="utf-8") as f:
        ids = [r["id"] for r in (json.loads(x) for x in f if x.strip()) if r.get("gt")]
    random.Random(seed).shuffle(ids)
    ids = ids[:n]
    async with async_session() as s:
        rows = dict((await s.execute(sql_text("SELECT id, content FROM chat_messages WHERE id = ANY(:i)"), {"i": ids})).all())
    await ensure_locator_alive()
    sem = asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=EVAL_LLM_TIMEOUT_S) as client:
        results = await asyncio.gather(*(one(client, sem, i, rows[i]) for i in ids if i in rows))
    with open(out, "w", encoding="utf-8") as fo:
        for r in results:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default="/tmp/paste_eval_v2.jsonl")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--out", default="/tmp/paste_answers.jsonl")
    ap.add_argument("--seed", type=int, default=20261005)
    a = ap.parse_args()
    asyncio.run(main(a.replay, a.n, a.out, a.seed))
