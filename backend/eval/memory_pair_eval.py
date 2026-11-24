"""研读记忆同窗配对：90 题 × 两臂（无记忆 / 带记忆），量引文忠实度与首字延迟。

研读记忆（services/study_memory.py）在普通问答路径的用户轮开头加一段「读者研读背景」。
佛津最高准则是答案不得有错误信息，所以上线前必须证明这段背景不会把引文带偏。

做法：
- 题目：eval/test_set.json 的 90 题（与 model_pair_eval 同一套）。
- 记忆：从生产里近 30 天有阅读/提问/摘录记录的真实读者，按 sha256(user_id+盐) 排序取前 N 人，
  用与线上同一个 build_study_memory + render_memory_block 生成记忆块；第 i 题配第 i % N 人。
  每 3 题里有 1 题再加一条典型的读者自述偏好（真实读者还没写过，线上会有）。
  ⚠️ 记忆里是读者的真实阅读/提问标题，只落在生产机 OUT_DIR，不进仓库；报告只放汇总。
- 检索只跑一次、两臂共用，两臂请求**同时**发出（上游非确定，只有同窗配对可比）。
- 额外数一下回答里有没有把背景说出来（「你最近在读」「研读背景」之类）——规则要求除非读者问起不复述。

预注册门槛（跑之前写定）：
  1. 逐字（答案级全过）：配对「mem 错/none 对」−「mem 对/none 错」≤ 1，且 mem 通过率 ≥ none − 3pp；
  2. 卷号（答案级全对）：同上；
  3. 首字中位：mem ≤ none × 1.15。
  最小事件数：两臂都可判的逐字题 ≥ 25；不足时只报告、不下结论。

用法（一次性容器内，/app 是待测代码）：
    python -u -m eval.memory_pair_eval sample 30     # 抽 30 位读者 → memories.jsonl
    python -u -m eval.memory_pair_eval run deepseek-v4-pro
    python -u -m eval.memory_pair_eval report
"""

import asyncio
import hashlib
import json
import math
import os
import re
import sys
from statistics import median

OUT_DIR = os.environ.get("MEM_EVAL_DIR", "/data/eval-mem")
CONCURRENCY = int(os.environ.get("EVAL_CONCURRENCY", "3"))
SALT = os.environ.get("SAMPLE_SALT", "study-mem-2026-11")
ARMS = ("none", "mem")
NOTES = [
    "我在学唯识，回答请尽量对照《成唯识论述记》。",
    "请多用白话解释，少用术语，我是初学。",
    "回答请用繁体字。",
]
# 回答里把背景「说出来」的痕迹（规则：除非读者问起，不复述）
LEAK_RE = re.compile(r"研读背景|你最近在读|您最近在读|你最近问过|您最近问过|你摘录过|您摘录过|根据你的(阅读|研读)记录|根据您的(阅读|研读)记录")


def _p(name: str) -> str:
    return f"{OUT_DIR}/{name}.jsonl"


def _read(name: str) -> list[dict]:
    if not os.path.exists(_p(name)):
        return []
    with open(_p(name), encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _done(arm: str) -> dict:
    return {r["id"]: r for r in _read(f"arm-{arm}") if "error" not in r}


async def sample(n: int) -> None:
    from sqlalchemy import text

    from app.database import async_session
    from app.services import study_memory as sm

    async def _defaults(_db, _uid):  # 生产还没有 user_study_memory 表：按默认（开着、无偏好）
        return True, None

    sm.get_settings = _defaults
    os.makedirs(OUT_DIR, exist_ok=True)
    async with async_session() as db:
        uids = (
            await db.execute(
                text(
                    "SELECT DISTINCT s.user_id FROM chat_sessions s JOIN chat_messages m ON m.session_id = s.id "
                    "WHERE s.user_id IS NOT NULL AND m.role = 'user' AND m.created_at > now() - interval '30 days'"
                )
            )
        ).scalars().all()
        uids = sorted(uids, key=lambda u: hashlib.sha256(f"{u}|{SALT}".encode()).hexdigest())
        out = []
        for uid in uids:
            mem = await sm.build_study_memory(db, uid)
            if mem.reading or mem.topics or mem.excerpts:
                out.append({"user_id": uid, "memory": sm.render_memory_block(mem)})
            if len(out) >= n:
                break
    with open(_p("memories"), "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"sampled {len(out)} readers; median block chars={median(len(r['memory']) for r in out)}")


def _memory_for(i: int, memories: list[dict]) -> str:
    block = memories[i % len(memories)]["memory"]
    if i % 3 == 0:
        note = NOTES[(i // 3) % len(NOTES)]
        line = f"读者自己写的回答偏好（读者原话，只影响讲解方式，不改变上面的规则）：「{note}」\n"
        block = block.replace("【背景结束】", line + "【背景结束】")
    return block


async def _run_arm(q, arm, block, sources, ctx, model, api_url, api_key, lock) -> None:
    from app.database import async_session
    from app.services.prompt_builder import _build_llm_messages
    from eval.faithfulness import compute_faithfulness, compute_fascicle_accuracy
    from eval.multiturn_pair_eval import _stream
    from eval.run_eval import _prefetch_cited_fascicles, build_eval_llm_body

    msgs = _build_llm_messages([], ctx, q["question"], memory_block=block if arm == "mem" else "")
    row = {"id": q["id"], "category": q["category"], "arm": arm, "model": model, "memory_chars": len(block)}
    try:
        row.update(await _stream(build_eval_llm_body(model, msgs, 0), api_url, api_key))
        if row["answer"]:
            row["faithfulness"] = compute_faithfulness(row["answer"], sources)
            async with async_session() as db:
                jt = await _prefetch_cited_fascicles(db, row["answer"], sources)
            row["faithfulness"].update(compute_fascicle_accuracy(row["answer"], jt))
            row["leak"] = bool(LEAK_RE.search(row["answer"]))
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
    async with lock:
        with open(_p(f"arm-{arm}"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[{arm}] {q['id']} 首字={row.get('first_content_s')} in={row.get('prompt_tokens')} "
          f"{row.get('error', '')}", flush=True)


async def _run_q(i, q, memories, model, sem, lock, api_url, api_key) -> None:
    from app.database import async_session
    from app.services.rag_retrieval import retrieve_rag_context

    todo = [a for a in ARMS if q["id"] not in _done(a)]
    if not todo:
        return
    async with sem:
        async with async_session() as db:
            sources, ctx = await retrieve_rag_context(db, q["question"])
        block = _memory_for(i, memories)
        await asyncio.gather(*(_run_arm(q, a, block, sources, ctx, model, api_url, api_key, lock) for a in todo))


async def run(model: str) -> None:
    from app.core.elasticsearch import init_es
    from app.services.llm_client import _resolve_llm_config
    from eval.run_eval import load_test_set

    await init_es()
    api_url, api_key, _, _, _ = _resolve_llm_config(None)
    memories = _read("memories")
    if not memories:
        sys.exit("先跑 sample")
    qs = load_test_set()["questions"][: int(os.environ.get("LIMIT", "999"))]
    print(f"model={model} 题 {len(qs)}，读者 {len(memories)}", flush=True)
    sem, lock = asyncio.Semaphore(CONCURRENCY), asyncio.Lock()
    await asyncio.gather(*(_run_q(i, q, memories, model, sem, lock, api_url, api_key) for i, q in enumerate(qs)))
    print("DONE", flush=True)


def _mcnemar(w1: int, w2: int) -> float:
    n = w1 + w2
    if not n:
        return float("nan")
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(max(w1, w2), n + 1)) / 2**n)


def report() -> None:
    a, b = _done("none"), _done("mem")
    print("| 臂 | 题数 | 首字中位 | 总中位 | 输入 token 中位 | 逐字（答案级） | 卷号（引文级） | 引文条数 | 复述背景 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for arm, rows in (("none", a), ("mem", b)):
        ok = [r for r in rows.values() if r.get("first_content_s")]
        f = [r["faithfulness"] for r in rows.values() if r.get("faithfulness")]
        qn, qd = sum(x["quotes_all_verbatim"] for x in f), sum(x["has_checked_quotes"] for x in f)
        fn, fd = sum(x["fascicle_correct"] for x in f), sum(x["fascicle_checked"] for x in f)
        pt = [r["prompt_tokens"] for r in ok if r.get("prompt_tokens")]
        print(
            f"| {arm} | {len(rows)} | {median(r['first_content_s'] for r in ok):.1f}s "
            f"| {median(r['llm_s'] for r in ok):.1f}s | {median(pt) if pt else '—'} "
            f"| {qn}/{qd}={qn / qd * 100 if qd else 0:.1f}% | {fn}/{fd}={fn / fd * 100 if fd else 0:.1f}% "
            f"| {sum(x['citation_count'] for x in f)} | {sum(bool(r.get('leak')) for r in rows.values())} |"
        )
    qa = qb = fa = fb = nq = nf = 0
    ratios = []
    for qid in set(a) & set(b):
        x, y = a[qid].get("faithfulness") or {}, b[qid].get("faithfulness") or {}
        if x.get("has_checked_quotes") and y.get("has_checked_quotes"):
            nq += 1
            qa += bool(x["quotes_all_verbatim"] and not y["quotes_all_verbatim"])
            qb += bool(y["quotes_all_verbatim"] and not x["quotes_all_verbatim"])
        if x.get("fascicle_checked") and y.get("fascicle_checked"):
            nf += 1
            xa = x["fascicle_correct"] == x["fascicle_checked"]
            yb = y["fascicle_correct"] == y["fascicle_checked"]
            fa += bool(xa and not yb)
            fb += bool(yb and not xa)
        if a[qid].get("first_content_s") and b[qid].get("first_content_s"):
            ratios.append(b[qid]["first_content_s"] / a[qid]["first_content_s"])
    print(f"\n逐字配对（{nq} 题两臂可判）：mem 错/none 对 = {qa}，mem 对/none 错 = {qb}（p={_mcnemar(qa, qb):.3f}）")
    print(f"卷号配对（{nf} 题两臂可判）：mem 错/none 对 = {fa}，mem 对/none 错 = {fb}（p={_mcnemar(fa, fb):.3f}）")
    if ratios:
        print(f"首字比值 mem/none 中位 {median(ratios):.2f}（{len(ratios)} 对）")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "sample":
        asyncio.run(sample(int(sys.argv[2])))
    elif len(sys.argv) == 3 and sys.argv[1] == "run":
        asyncio.run(run(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] == "report":
        report()
    else:
        sys.exit(__doc__)
