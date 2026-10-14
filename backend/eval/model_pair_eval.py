"""两个模型同窗配对：90 题，量首字/总耗时 + 确定性引文忠实度（不调 LLM 判官）。

为什么不直接用 run_eval.py：它是非流式调用，量不到「首个正文字」——那才是用户
真正等待的时间；而且它每题还要调一次 LLM 判官，配对比较用不上、白花钱。

检索、提示词（含引文纪律后缀）、max_tokens、思考字段与 run_eval 同口径，
temperature 固定 0。⚠️ 两臂必须**同时段并行**跑：上游非确定，同参跨时段单轮
可差 9.5pp，只有同窗配对可比。

2026-10-14 首用：pro vs flash，首字中位 52.5s vs 9.7s，但逐字引用保真度
94.8% vs 67.7%、卷号准确率 95.5% vs 85.5%，配对 17:2（p=0.001）→ 不换。
一轮 90 题 pro 约 ¥9、flash 约 ¥3。

用法（生产容器内，结果写 /data/eval-pair/<tag>.jsonl，重跑跳过已完成的题）：
    python -m eval.model_pair_eval run arm-pro deepseek-v4-pro &
    python -m eval.model_pair_eval run arm-flash deepseek-v4-flash &
    python -m eval.model_pair_eval report arm-pro arm-flash
环境变量 LIMIT=N 只跑前 N 题（先拿 1 题试通再全量）。
"""

import asyncio
import json
import math
import os
import sys
import time
from statistics import median

OUT_DIR = os.environ.get("PAIR_EVAL_DIR", "/data/eval-pair")
CONCURRENCY = int(os.environ.get("EVAL_CONCURRENCY", "3"))


def _path(tag: str) -> str:
    return f"{OUT_DIR}/{tag}.jsonl"


def _load(tag: str) -> dict:
    rows: dict = {}
    if os.path.exists(_path(tag)):
        with open(_path(tag), encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    if "error" not in r:
                        rows.setdefault(r["id"], r)
    return rows


async def _run_one(q, tag, model, sem, lock, api_url, api_key):
    import httpx

    from app.database import async_session
    from app.services.chat import _build_llm_messages
    from app.services.rag_retrieval import retrieve_rag_context
    from eval.faithfulness import compute_faithfulness, compute_fascicle_accuracy
    from eval.run_eval import _prefetch_cited_fascicles, build_eval_llm_body

    async with sem:
        row = {"id": q["id"], "category": q["category"], "question": q["question"], "model": model}
        try:
            async with async_session() as db:
                sources, ctx = await retrieve_rag_context(db, q["question"])
            body = build_eval_llm_body(model, _build_llm_messages([], ctx, q["question"]), 0)
            body["stream"] = True
            t1 = time.monotonic()
            first_content = None
            answer, reasoning_chars, finish = [], 0, None
            async with (
                httpx.AsyncClient(timeout=httpx.Timeout(300, connect=20)) as c,
                c.stream(
                    "POST",
                    f"{api_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                ) as resp,
            ):
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    choices = json.loads(data)["choices"]
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    reasoning_chars += len(delta.get("reasoning_content") or "")
                    if delta.get("content"):
                        first_content = first_content or time.monotonic()
                        answer.append(delta["content"])
                    finish = choices[0].get("finish_reason") or finish
            ans = "".join(answer)
            row.update(
                {
                    "first_content_s": round(first_content - t1, 2) if first_content else None,
                    "llm_s": round(time.monotonic() - t1, 2),
                    "reasoning_chars": reasoning_chars,
                    "answer_chars": len(ans),
                    "finish_reason": finish,
                    "answer": ans,
                }
            )
            if ans:
                row["faithfulness"] = compute_faithfulness(ans, sources)
                async with async_session() as db2:
                    juan_text = await _prefetch_cited_fascicles(db2, ans, sources)
                row["faithfulness"].update(compute_fascicle_accuracy(ans, juan_text))
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        async with lock:
            with open(_path(tag), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            f"[{tag}] {row['id']} 首字={row.get('first_content_s')} 总={row.get('llm_s')} {row.get('error', '')}",
            flush=True,
        )


async def run(tag: str, model: str) -> None:
    from app.core.elasticsearch import init_es
    from app.services.chat import _resolve_llm_config
    from eval.run_eval import load_test_set

    os.makedirs(OUT_DIR, exist_ok=True)
    await init_es()
    api_url, api_key, _, _, _ = _resolve_llm_config(None)
    done = _load(tag)
    todo = [q for q in load_test_set()["questions"] if q["id"] not in done]
    todo = todo[: int(os.environ.get("LIMIT", "999"))]
    print(f"[{tag}] model={model} 本轮 {len(todo)} 题", flush=True)
    sem, lock = asyncio.Semaphore(CONCURRENCY), asyncio.Lock()
    await asyncio.gather(*(_run_one(q, tag, model, sem, lock, api_url, api_key) for q in todo))
    print(f"[{tag}] DONE", flush=True)


def _p90(xs: list) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(0.9 * (len(xs) - 1)))]


def _mcnemar(w1: int, w2: int) -> float:
    n = w1 + w2
    if not n:
        return float("nan")
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(max(w1, w2), n + 1)) / 2**n)


def report(tag_a: str, tag_b: str) -> None:
    a, b = _load(tag_a), _load(tag_b)
    print("| 臂 | 题数 | 首字中位 | 首字p90 | 总中位 | 逐字保真度 | 卷号准确率 | 引文条数 |")
    print("|---|---|---|---|---|---|---|---|")
    for tag, rows in ((tag_a, a), (tag_b, b)):
        ok = [r for r in rows.values() if r.get("first_content_s")]
        f = [r["faithfulness"] for r in rows.values() if r.get("faithfulness")]
        qn, qd = sum(x["quotes_all_verbatim"] for x in f), sum(x["has_checked_quotes"] for x in f)
        fn, fd = sum(x["fascicle_correct"] for x in f), sum(x["fascicle_checked"] for x in f)
        fc = [r["first_content_s"] for r in ok]
        print(
            f"| {tag} | {len(rows)} | {median(fc):.1f}s | {_p90(fc):.1f}s "
            f"| {median(r['llm_s'] for r in ok):.1f}s "
            f"| {qn}/{qd}={qn / qd * 100 if qd else 0:.1f}% | {fn}/{fd}={fn / fd * 100 if fd else 0:.1f}% "
            f"| {sum(x['citation_count'] for x in f)} |"
        )

    # 配对：同题两臂都有可查引文 / 可核卷号时，谁对谁错
    qa = qb = fa = fb = 0
    for qid in set(a) & set(b):
        x, y = a[qid].get("faithfulness") or {}, b[qid].get("faithfulness") or {}
        if x.get("has_checked_quotes") and y.get("has_checked_quotes"):
            qa += bool(x["quotes_all_verbatim"] and not y["quotes_all_verbatim"])
            qb += bool(y["quotes_all_verbatim"] and not x["quotes_all_verbatim"])
        if x.get("fascicle_checked") and y.get("fascicle_checked"):
            xa = x["fascicle_correct"] == x["fascicle_checked"]
            yb = y["fascicle_correct"] == y["fascicle_checked"]
            fa += bool(xa and not yb)
            fb += bool(yb and not xa)
    print(f"\n逐字配对 {tag_a} 对/{tag_b} 错 = {qa}:{qb}（p={_mcnemar(qa, qb):.3f}）")
    print(f"卷号配对 {tag_a} 对/{tag_b} 错 = {fa}:{fb}（p={_mcnemar(fa, fb):.3f}）")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "run":
        sys.path.insert(0, "/app")
        asyncio.run(run(sys.argv[2], sys.argv[3]))
    elif len(sys.argv) == 4 and sys.argv[1] == "report":
        report(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
