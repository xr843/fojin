"""多轮回放同窗配对：旧上下文窗口（6000 token / 10 条）vs 新窗口，同题同窗两臂。

现有 eval 全是单轮题，量不到「历史带多少」这个改动。这里从生产 chat_messages
抽长会话，取会话靠后的一个真实提问当测试点，历史用该点之前的真实消息，
检索只跑一次、两臂共用（唯一变量是带入多少历史），两臂**同时**发出请求。

⚠️ 用户对话内容只落在生产机 /data/eval-mt/（OUT_DIR），不进仓库；报告只放汇总。

指标：
- 确定性引文忠实度：逐字引文通过率、卷号准确率（与 model_pair_eval 同一套核验）
- 首字延迟（流式第一个正文字）、上游计费的输入 token（usage.prompt_tokens）
- 上下文保持（LLM 裁判，deepseek-v4-flash 关思考，盲评、不知道是哪一臂）：
  答案是否承接了「旧窗口看不到的那段早期讨论」

用法（生产容器/一次性容器内，/app 是待测代码）：
    python -u -m eval.multiturn_pair_eval sample 40      # 哈希抽会话 → cases.jsonl
    python -u -m eval.multiturn_pair_eval run deepseek-v4-pro   # 两臂同窗，断点续跑
    python -u -m eval.multiturn_pair_eval judge          # 上下文保持裁判，断点续跑
    python -u -m eval.multiturn_pair_eval report
环境变量：NEW_MAX_INPUT / NEW_MAX_MESSAGES（新臂窗口，默认 16000/20）、
SAMPLE_SALT（抽样盐）、LIMIT、EVAL_CONCURRENCY。
"""

import asyncio
import hashlib
import json
import math
import os
import sys
import time
from statistics import median
from types import SimpleNamespace

OUT_DIR = os.environ.get("MT_EVAL_DIR", "/data/eval-mt")
CONCURRENCY = int(os.environ.get("EVAL_CONCURRENCY", "3"))
SALT = os.environ.get("SAMPLE_SALT", "mt-ctx-2026-10")
ARMS = {
    "old": (6000, 10),
    "new": (int(os.environ.get("NEW_MAX_INPUT", "16000")), int(os.environ.get("NEW_MAX_MESSAGES", "20"))),
}
MIN_PRIOR = 10  # 测试点之前至少 10 条消息，即「第 10 条之后」的提问
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "deepseek-v4-flash")


def _p(name: str) -> str:
    return f"{OUT_DIR}/{name}.jsonl"


def _read(name: str) -> list[dict]:
    if not os.path.exists(_p(name)):
        return []
    with open(_p(name), encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _done(name: str) -> dict:
    return {r["key"]: r for r in _read(name) if "error" not in r}


def _h(*parts) -> str:
    return hashlib.sha256(("|".join(map(str, parts)) + "|" + SALT).encode()).hexdigest()


# ── sample ──────────────────────────────────────────────────────────────────


async def sample(n: int) -> None:
    from sqlalchemy import text

    from app.database import async_session

    async with async_session() as db:
        sids = (
            await db.execute(
                text(
                    "SELECT session_id FROM chat_messages GROUP BY session_id "
                    "HAVING count(*) > 10 AND max(created_at) > now() - interval '90 days'"
                )
            )
        ).scalars().all()
        # 按 sha256(会话 id + 盐) 排序取前 n —— 与 id 奇偶、时间先后都无关
        picked = sorted(sids, key=lambda s: _h("session", s))
        cases = []
        for sid in picked:
            rows = (
                await db.execute(
                    text(
                        "SELECT id, role, content FROM chat_messages WHERE session_id = :s "
                        "ORDER BY created_at, id"
                    ),
                    {"s": sid},
                )
            ).all()
            points = [i for i, r in enumerate(rows) if r.role == "user" and i >= MIN_PRIOR and r.content.strip()]
            if not points:
                continue
            # 靠后的提问里按哈希挑一个（会话后半段）
            late = points[len(points) // 2 :]
            i = min(late, key=lambda k: _h("point", rows[k].id))
            history = [{"role": r.role, "content": r.content} for r in rows[:i]]
            cases.append(
                {
                    "key": f"s{sid}",
                    "question": rows[i].content,
                    "position": i + 1,
                    "session_len": len(rows),
                    "history": history,
                }
            )
            if len(cases) >= n:
                break
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(_p("cases"), "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"候选会话 {len(sids)}，写入 {len(cases)} 题 → {_p('cases')}", flush=True)


# ── run ─────────────────────────────────────────────────────────────────────


def _build(case: dict, ctx: str, arm: str) -> tuple[list[dict], int]:
    """按某一臂的窗口拼消息。同步、无 await —— 改全局 settings 是安全的。"""
    from app.config import settings
    from app.services.prompt_builder import _build_llm_messages

    hist = [SimpleNamespace(**m) for m in case["history"]]
    saved = settings.chat_max_input_tokens, settings.chat_history_max_messages
    settings.chat_max_input_tokens, settings.chat_history_max_messages = ARMS[arm]
    try:
        msgs = _build_llm_messages(hist, ctx, case["question"])
    finally:
        settings.chat_max_input_tokens, settings.chat_history_max_messages = saved
    return msgs, len(msgs) - 2


async def _stream(body: dict, api_url: str, api_key: str) -> dict:
    import httpx

    body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    t1 = time.monotonic()
    first, answer, reasoning, finish, usage = None, [], 0, None, {}
    async with (
        httpx.AsyncClient(timeout=httpx.Timeout(400, connect=20)) as c,
        c.stream("POST", f"{api_url}/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=body) as r,
    ):
        r.raise_for_status()
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            obj = json.loads(data)
            usage = obj.get("usage") or usage
            if not obj.get("choices"):
                continue
            ch = obj["choices"][0]
            delta = ch.get("delta") or {}
            reasoning += len(delta.get("reasoning_content") or "")
            if delta.get("content"):
                first = first or time.monotonic()
                answer.append(delta["content"])
            finish = ch.get("finish_reason") or finish
    return {
        "first_content_s": round(first - t1, 2) if first else None,
        "llm_s": round(time.monotonic() - t1, 2),
        "reasoning_chars": reasoning,
        "finish_reason": finish,
        "prompt_tokens": usage.get("prompt_tokens"),
        "cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
        "answer": "".join(answer),
    }


async def _run_arm(case, arm, sources, ctx, model, api_url, api_key, lock) -> None:
    from app.database import async_session
    from eval.faithfulness import compute_faithfulness, compute_fascicle_accuracy
    from eval.run_eval import _prefetch_cited_fascicles, build_eval_llm_body

    msgs, n_hist = _build(case, ctx, arm)
    row = {"key": case["key"], "arm": arm, "model": model, "history_included": n_hist,
           "history_available": len(case["history"])}
    try:
        row.update(await _stream(build_eval_llm_body(model, msgs, 0), api_url, api_key))
        if row["answer"]:
            row["faithfulness"] = compute_faithfulness(row["answer"], sources)
            async with async_session() as db:
                jt = await _prefetch_cited_fascicles(db, row["answer"], sources)
            row["faithfulness"].update(compute_fascicle_accuracy(row["answer"], jt))
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
    async with lock:
        with open(_p(f"arm-{arm}"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[{arm}] {case['key']} hist={n_hist}/{len(case['history'])} 首字={row.get('first_content_s')} "
          f"in={row.get('prompt_tokens')} {row.get('error', '')}", flush=True)


async def _run_case(case, model, sem, lock, api_url, api_key) -> None:
    from app.database import async_session
    from app.services.prompt_builder import _is_meta_question
    from app.services.rag_retrieval import retrieve_rag_context

    todo = [a for a in ARMS if case["key"] not in _done(f"arm-{a}")]
    if not todo:
        return
    async with sem:
        # 与生产同口径：上一条用户提问前 200 字参与检索；meta 问题不检索
        prev = next((m["content"][:200] for m in reversed(case["history"]) if m["role"] == "user"), None)
        if _is_meta_question(case["question"]):
            sources, ctx = [], ""
        else:
            async with async_session() as db:
                sources, ctx = await retrieve_rag_context(db, case["question"], prev_query=prev)
        # 两臂同时发出 —— 同窗配对的关键
        await asyncio.gather(*(_run_arm(case, a, sources, ctx, model, api_url, api_key, lock) for a in todo))


async def run(model: str) -> None:
    from app.core.elasticsearch import init_es
    from app.services.llm_client import _resolve_llm_config

    await init_es()
    api_url, api_key, _, _, _ = _resolve_llm_config(None)
    cases = _read("cases")[: int(os.environ.get("LIMIT", "9999"))]
    print(f"model={model} 窗口={ARMS} 共 {len(cases)} 题", flush=True)
    sem, lock = asyncio.Semaphore(CONCURRENCY), asyncio.Lock()
    await asyncio.gather(*(_run_case(c, model, sem, lock, api_url, api_key) for c in cases))
    print("DONE", flush=True)


# ── judge：上下文保持 ─────────────────────────────────────────────────────────

_JUDGE_PROMPT = """你在评估一段佛学研读对话里，AI 助手的回答是否承接了较早的讨论。

【较早的讨论】（这段对话更早的部分）
{early}

【之后的若干轮】（略）

【用户当前提问】
{question}

【助手回答】
{answer}

请只输出一行 JSON：{{"needs_early": true/false, "uses_early": true/false}}
- needs_early：要答好当前提问，是否需要用到「较早的讨论」里的具体内容（如指代前文、接着前面的段落/论点继续、延续前面约定的体例）。
- uses_early：助手回答是否确实承接或利用了「较早的讨论」中的具体内容（只是话题相同、泛泛提到同一部经不算）。"""


async def _judge_one(case, arm_row, early, api_url, api_key, sem, lock) -> None:
    import httpx

    key = f"{case['key']}:{arm_row['arm']}"
    async with sem:
        body = {
            "model": JUDGE_MODEL,
            "messages": [{"role": "user", "content": _JUDGE_PROMPT.format(
                early=early, question=case["question"][:2000], answer=arm_row["answer"][:4000])}],
            "temperature": 0,
            "max_tokens": 100,
            "thinking": {"type": "disabled"},
        }
        row = {"key": key}
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(f"{api_url}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                                 json=body)
                r.raise_for_status()
                out = r.json()["choices"][0]["message"]["content"]
            j = json.loads(out[out.index("{"): out.rindex("}") + 1])
            row.update({"needs_early": bool(j["needs_early"]), "uses_early": bool(j["uses_early"])})
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        async with lock:
            with open(_p("judge"), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


async def judge() -> None:
    from app.services.llm_client import _resolve_llm_config

    api_url, api_key, _, _, _ = _resolve_llm_config(None)
    cases = {c["key"]: c for c in _read("cases")}
    arms = {a: _done(f"arm-{a}") for a in ARMS}
    done = _done("judge")
    sem, lock, jobs = asyncio.Semaphore(6), asyncio.Lock(), []
    for k, case in cases.items():
        old = arms["old"].get(k)
        if not old or not all(arms[a].get(k, {}).get("answer") for a in ARMS):
            continue
        # 「较早的讨论」= 旧窗口看不到的那部分历史（取其中最靠后的 6000 字）
        dropped = case["history"][: len(case["history"]) - old["history_included"]]
        early = "\n\n".join(f"[{'用户' if m['role'] == 'user' else '助手'}] {m['content'][:1500]}" for m in dropped)
        early = early[-6000:]
        for a in ARMS:
            if f"{k}:{a}" not in done:
                jobs.append(_judge_one(case, arms[a][k], early, api_url, api_key, sem, lock))
    print(f"裁判 {len(jobs)} 份", flush=True)
    await asyncio.gather(*jobs)
    print("DONE", flush=True)


# ── report ──────────────────────────────────────────────────────────────────


def _mcnemar(w1: int, w2: int) -> float:
    n = w1 + w2
    if not n:
        return float("nan")
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(max(w1, w2), n + 1)) / 2**n)


def report() -> None:
    o, n = _done("arm-old"), _done("arm-new")
    keys = sorted(set(o) & set(n))
    print(f"配对完成 {len(keys)} 题（old {len(o)} / new {len(n)}）\n")
    print("| 臂 | 窗口 | 带入历史条数中位 | 输入token中位 | 首字中位 | 首字p90 | 总耗时中位 | 逐字通过（答案级） "
          "| 被查引文段 | 卷号准确率 | 引文条数 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for arm, rows in (("old", o), ("new", n)):
        rs = [rows[k] for k in keys]
        f = [r["faithfulness"] for r in rs if r.get("faithfulness")]
        qn, qd = sum(x["quotes_all_verbatim"] for x in f), sum(x["has_checked_quotes"] for x in f)
        fn, fd = sum(x["fascicle_correct"] for x in f), sum(x["fascicle_checked"] for x in f)
        fc = sorted(r["first_content_s"] for r in rs if r.get("first_content_s"))
        pt = [r["prompt_tokens"] for r in rs if r.get("prompt_tokens")]
        print(
            f"| {arm} | {ARMS[arm][0]}/{ARMS[arm][1]} | {median(r['history_included'] for r in rs)} "
            f"| {median(pt) if pt else '-'} | {median(fc):.1f}s | {fc[min(len(fc) - 1, round(0.9 * (len(fc) - 1)))]:.1f}s "
            f"| {median(r['llm_s'] for r in rs):.1f}s | {qn}/{qd}={qn / qd * 100 if qd else 0:.1f}% "
            f"| {sum(x['quote_count'] for x in f)} | {fn}/{fd}={fn / fd * 100 if fd else 0:.1f}% "
            f"| {sum(x['citation_count'] for x in f)} |"
        )
    qo = qn_ = fo = fn_ = qboth = fboth = 0
    lat = []
    for k in keys:
        x, y = o[k].get("faithfulness") or {}, n[k].get("faithfulness") or {}
        if x.get("has_checked_quotes") and y.get("has_checked_quotes"):
            qboth += 1
            qo += bool(x["quotes_all_verbatim"] and not y["quotes_all_verbatim"])
            qn_ += bool(y["quotes_all_verbatim"] and not x["quotes_all_verbatim"])
        if x.get("fascicle_checked") and y.get("fascicle_checked"):
            fboth += 1
            xa, yb = x["fascicle_correct"] == x["fascicle_checked"], y["fascicle_correct"] == y["fascicle_checked"]
            fo += bool(xa and not yb)
            fn_ += bool(yb and not xa)
        if o[k].get("first_content_s") and n[k].get("first_content_s"):
            lat.append(n[k]["first_content_s"] / o[k]["first_content_s"])
    print(f"\n逐字：两臂都有可查引文 {qboth} 题；配对 new 对/old 错 = {qn_}:{qo}（p={_mcnemar(qn_, qo):.3f}）")
    print(f"卷号：两臂都有可核卷号 {fboth} 题；配对 new 对/old 错 = {fn_}:{fo}（p={_mcnemar(fn_, fo):.3f}）")
    if lat:
        print(f"首字配对比值 new/old 中位 {median(lat):.2f}（{len(lat)} 对）")

    j = _done("judge")
    if j:
        print("\n上下文保持（LLM 裁判 deepseek-v4-flash 关思考，盲评）：")
        for arm in ARMS:
            js = [j[f"{k}:{arm}"] for k in keys if f"{k}:{arm}" in j]
            need = [x for x in js if x["needs_early"]]
            print(f"  {arm}: 承接早期讨论 {sum(x['uses_early'] for x in js)}/{len(js)}；"
                  f"其中裁判认为需要早期讨论的题 {sum(x['uses_early'] for x in need)}/{len(need)}")
        w = l_ = 0
        for k in keys:
            a, b = j.get(f"{k}:old"), j.get(f"{k}:new")
            if a and b:
                w += bool(b["uses_early"] and not a["uses_early"])
                l_ += bool(a["uses_early"] and not b["uses_early"])
        print(f"  配对 new 承接/old 未承接 = {w}:{l_}（p={_mcnemar(w, l_):.3f}）")


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sample":
        asyncio.run(sample(int(sys.argv[2]) if len(sys.argv) > 2 else 40))
    elif cmd == "run" and len(sys.argv) == 3:
        asyncio.run(run(sys.argv[2]))
    elif cmd == "judge":
        asyncio.run(judge())
    elif cmd == "report":
        report()
    else:
        sys.exit(__doc__)
