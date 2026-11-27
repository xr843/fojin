"""检索段落附夹注 同窗配对：真实提问 × 两臂（不附夹注 / 附夹注），量引文忠实度、首字延迟与答案优劣。

夹注（CBETA 双行小注）此前全被解析器丢掉，2026-11-27 起阅读页可见；但 AI 问答检索到的段落仍不含夹注，
注疏里夹注常是作者自己的释文（楞严经疏解蒙钞 57%）。services/inline_note_context.py 在交给模型的上下文里
把夹注按位置以「（…）」插回段落，chunk_text 与引文核对不变。佛津最高准则是答案不得有错，上线前必须过本评测。

做法：
- 题目：生产近 90 天真实提问，限会话首问（无上文），其回答引用过夹注占全书 ≥10% 的经；按 sha256(id+盐) 取。
  ⚠️ 提问原文只落在生产机 OUT_DIR，不进仓库；报告只放汇总。
- 检索只跑一次、两臂共用（检索结果完全相同，只差上下文里有无夹注）；两臂请求同时发出。
  检索段落一条夹注都没附上的题跳过（两臂完全相同，不可比）。
- 逐字 / 卷号：与线上同一套 compute_faithfulness（对照不含夹注的 sources）——模型若把夹注原话当引文，
  线上会被降级，这里同样记为不过，量的就是线上真实效果。
- 盲评：同一模型、温度 0，给题目、附夹注的检索原文、两份答案（A/B 次序按哈希打乱），判哪份更准确、更切题，
  并分别数出与原文或常识相悖的错误条数。

预注册门槛（跑之前写定，2026-11-27）：
  1. 逐字（答案级全过）：配对「notes 错/none 对」−「notes 对/none 错」≤ 1，且 notes 通过率 ≥ none − 3pp；
  2. 卷号（答案级全对）：同上；
  3. 首字中位：notes ≤ none × 1.15；
  4. 盲评：notes 胜 − notes 负 ≥ 判定题数 × 20%，且 notes 错误总条数 ≤ none。
  最小事件数：真附上夹注的题 ≥ 25；不足时只报告、不下结论。
  四条全过才开 settings.rag_inline_notes。

用法（一次性容器内，/app 是待测代码）：
    python -u -m eval.notes_pair_eval sample 45
    python -u -m eval.notes_pair_eval run deepseek-v4-pro
    python -u -m eval.notes_pair_eval judge deepseek-v4-pro
    python -u -m eval.notes_pair_eval report
"""

import asyncio
import hashlib
import json
import math
import os
import re
import sys
from statistics import median

OUT_DIR = os.environ.get("NOTES_EVAL_DIR", "/data/eval-notes")
CONCURRENCY = int(os.environ.get("EVAL_CONCURRENCY", "3"))
SALT = os.environ.get("SAMPLE_SALT", "inline-notes-2026-11")
ARMS = ("none", "notes")


def _p(name: str) -> str:
    return f"{OUT_DIR}/{name}.jsonl"


def _read(name: str) -> list[dict]:
    if not os.path.exists(_p(name)):
        return []
    with open(_p(name), encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _done(name: str) -> dict:
    return {r["id"]: r for r in _read(name) if "error" not in r}


async def sample(n: int) -> None:
    from sqlalchemy import text

    from app.database import async_session

    os.makedirs(OUT_DIR, exist_ok=True)
    sql = text("""
        with heavy as (
          select n.text_id from text_inline_notes n join buddhist_texts b on b.id = n.text_id
          group by n.text_id, b.content_char_count
          having sum(length(n.content)) >= 0.1 * (b.content_char_count + sum(length(n.content)))
        ), cited as (
          select distinct m.session_id, m.id from chat_messages m,
            json_array_elements(case when json_typeof(m.sources) = 'array' then m.sources else '[]'::json end) s
          where m.role = 'assistant' and m.created_at > now() - interval '90 days'
            and (s->>'text_id')::int in (select text_id from heavy)
        ), firstq as (
          select distinct on (m.session_id) m.session_id, m.id, m.content
          from chat_messages m where m.role = 'user' order by m.session_id, m.id
        )
        select distinct f.id, f.content from firstq f join cited c on c.session_id = f.session_id
          and c.id > f.id
          and not exists (select 1 from chat_messages x where x.session_id = f.session_id and x.role = 'user'
                          and x.id > f.id and x.id < c.id)
    """)
    async with async_session() as db:
        rows = (await db.execute(sql)).all()
    seen: set[str] = set()
    qs = []
    for mid, content in sorted(rows, key=lambda r: hashlib.sha256(f"{r[0]}|{SALT}".encode()).hexdigest()):
        q = (content or "").strip()
        key = re.sub(r"\s+", "", q)
        if not (6 <= len(q) <= 300) or key in seen:
            continue
        seen.add(key)
        qs.append({"id": f"q{mid}", "question": q})
        if len(qs) >= n:
            break
    with open(_p("questions"), "w", encoding="utf-8") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"候选首问 {len(rows)}，取 {len(qs)} 题")


async def _run_arm(q, arm, ctx, sources, model, api_url, api_key, lock) -> None:
    from app.database import async_session
    from app.services.prompt_builder import _build_llm_messages
    from eval.faithfulness import compute_faithfulness, compute_fascicle_accuracy
    from eval.multiturn_pair_eval import _stream
    from eval.run_eval import _prefetch_cited_fascicles, build_eval_llm_body

    msgs = _build_llm_messages([], ctx, q["question"])
    row = {"id": q["id"], "arm": arm, "model": model, "ctx_chars": len(ctx)}
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
    print(f"[{arm}] {q['id']} 首字={row.get('first_content_s')} 上下文={len(ctx)} {row.get('error', '')}", flush=True)


async def _run_q(q, model, sem, lock, api_url, api_key) -> None:
    from app.database import async_session
    from app.services.inline_note_context import chunks_with_notes
    from app.services.rag_retrieval import retrieve_rag_context

    todo = [a for a in ARMS if q["id"] not in _done(f"arm-{a}")]
    if not todo or q["id"] in {r["id"] for r in _read("skipped")}:
        return
    async with sem:
        async with async_session() as db:
            sources, ctx = await retrieve_rag_context(db, q["question"])
            spliced = await chunks_with_notes(db, [s.model_dump() for s in sources])
        ctx_notes = ctx
        for i, body in spliced.items():
            ctx_notes = ctx_notes.replace(sources[i].chunk_text, body, 1)
        if ctx_notes == ctx:
            async with lock:
                with open(_p("skipped"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"id": q["id"], "reason": "no notes attached"}) + "\n")
            print(f"[skip] {q['id']} 检索段落没有夹注", flush=True)
            return
        async with lock:
            with open(_p("contexts"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"id": q["id"], "ctx_notes": ctx_notes, "added": len(ctx_notes) - len(ctx),
                                    "chunks": len(spliced)}, ensure_ascii=False) + "\n")  # fmt: skip
        arm_ctx = {"none": ctx, "notes": ctx_notes}
        await asyncio.gather(*(_run_arm(q, a, arm_ctx[a], sources, model, api_url, api_key, lock) for a in todo))


async def run(model: str) -> None:
    from app.core.elasticsearch import init_es
    from app.services.llm_client import _resolve_llm_config

    await init_es()
    api_url, api_key, _, _, _ = _resolve_llm_config(None)
    qs = _read("questions")
    if not qs:
        sys.exit("先跑 sample")
    print(f"model={model} 题 {len(qs)}", flush=True)
    sem, lock = asyncio.Semaphore(CONCURRENCY), asyncio.Lock()
    await asyncio.gather(*(_run_q(q, model, sem, lock, api_url, api_key) for q in qs))
    print("DONE", flush=True)


JUDGE_SYSTEM = (
    "你是佛教文献审校。下面给出一个读者问题、检索到的原文（括号小字是原书夹注，同样是原文的一部分）、"
    "以及两份回答 A、B。请只依据原文与公认的佛学常识判断：\n"
    "1. 哪份回答对读者的问题更准确、更切题（不因篇幅长而加分）；\n"
    "2. 两份回答各有几处与原文或常识相悖的错误（错引、张冠李戴、编造出处、讲错义理都算）。\n"
    '只输出一行 JSON：{"better": "A" 或 "B" 或 "tie", "errors_A": 整数, "errors_B": 整数, "reason": "一句话"}'
)


async def _judge_one(q, a_none, a_notes, ctx_notes, model, api_url, api_key, lock) -> None:
    from eval.multiturn_pair_eval import _stream
    from eval.run_eval import build_eval_llm_body

    flip = int(hashlib.sha256(f"{q['id']}|{SALT}".encode()).hexdigest(), 16) % 2 == 1
    A, B = (a_notes, a_none) if flip else (a_none, a_notes)
    user = f"【问题】\n{q['question']}\n\n【检索原文】\n{ctx_notes}\n\n【回答 A】\n{A}\n\n【回答 B】\n{B}"
    msgs = [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]
    row = {"id": q["id"], "flip": flip}
    try:
        r = await _stream(build_eval_llm_body(model, msgs, 0), api_url, api_key)
        m = re.search(r"\{.*\}", r["answer"] or "", re.S)
        v = json.loads(m.group(0)) if m else {}
        better = v.get("better")
        # 还原成两臂：notes 是 A 还是 B
        notes_letter, none_letter = ("A", "B") if flip else ("B", "A")
        row.update({
            "winner": "notes" if better == notes_letter else "none" if better == none_letter else "tie",
            "errors_notes": int(v.get(f"errors_{notes_letter}", 0) or 0),
            "errors_none": int(v.get(f"errors_{none_letter}", 0) or 0),
            "reason": v.get("reason", ""),
        })  # fmt: skip
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
    async with lock:
        with open(_p("judge"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[judge] {q['id']} {row.get('winner')} {row.get('error', '')}", flush=True)


async def judge(model: str) -> None:
    from app.services.llm_client import _resolve_llm_config

    api_url, api_key, _, _, _ = _resolve_llm_config(None)
    qs = {q["id"]: q for q in _read("questions")}
    a, b = _done("arm-none"), _done("arm-notes")
    ctxs = {r["id"]: r["ctx_notes"] for r in _read("contexts")}
    done = _done("judge")
    sem, lock = asyncio.Semaphore(CONCURRENCY), asyncio.Lock()

    async def one(qid):
        async with sem:
            await _judge_one(qs[qid], a[qid]["answer"], b[qid]["answer"], ctxs[qid], model, api_url, api_key, lock)

    todo = [qid for qid in set(a) & set(b) if qid not in done and a[qid].get("answer") and b[qid].get("answer")]
    await asyncio.gather(*(one(qid) for qid in todo))
    print("DONE", flush=True)


def _mcnemar(w1: int, w2: int) -> float:
    n = w1 + w2
    if not n:
        return float("nan")
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(max(w1, w2), n + 1)) / 2**n)


def report() -> None:
    a, b = _done("arm-none"), _done("arm-notes")
    ctxs = {r["id"]: r for r in _read("contexts")}
    print(f"题目 {len(_read('questions'))}；检索段落没有夹注而跳过 {len(_read('skipped'))}；两臂都答完 {len(set(a) & set(b))}")
    if ctxs:
        print(f"附夹注：每题平均 {sum(r['chunks'] for r in ctxs.values()) / len(ctxs):.1f} 段，"
              f"上下文中位多 {median(r['added'] for r in ctxs.values())} 字")  # fmt: skip
    print("| 臂 | 题数 | 首字中位 | 总中位 | 输入 token 中位 | 逐字（答案级） | 卷号（答案级） |")
    print("|---|---|---|---|---|---|---|")
    for arm, rows in (("none", a), ("notes", b)):
        ok = [r for r in rows.values() if r.get("first_content_s")]
        f = [r["faithfulness"] for r in rows.values() if r.get("faithfulness")]
        qn, qd = sum(x["quotes_all_verbatim"] for x in f), sum(x["has_checked_quotes"] for x in f)
        fn = sum(x["fascicle_correct"] == x["fascicle_checked"] for x in f if x["fascicle_checked"])
        fd = sum(bool(x["fascicle_checked"]) for x in f)
        pt = [r["prompt_tokens"] for r in ok if r.get("prompt_tokens")]
        print(
            f"| {arm} | {len(rows)} | {median(r['first_content_s'] for r in ok):.1f}s | {median(r['llm_s'] for r in ok):.1f}s "
            f"| {median(pt) if pt else '—'} | {qn}/{qd}={qn / qd * 100 if qd else 0:.1f}% "
            f"| {fn}/{fd}={fn / fd * 100 if fd else 0:.1f}% |"
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
    print(f"\n逐字配对（{nq} 题两臂可判）：notes 错/none 对 = {qa}，notes 对/none 错 = {qb}（p={_mcnemar(qa, qb):.3f}）")
    print(f"卷号配对（{nf} 题两臂可判）：notes 错/none 对 = {fa}，notes 对/none 错 = {fb}（p={_mcnemar(fa, fb):.3f}）")
    if ratios:
        print(f"首字比值 notes/none 中位 {median(ratios):.2f}（{len(ratios)} 对）")
    j = list(_done("judge").values())
    if j:
        w = sum(r["winner"] == "notes" for r in j)
        lo = sum(r["winner"] == "none" for r in j)
        en, eo = sum(r["errors_notes"] for r in j), sum(r["errors_none"] for r in j)
        print(f"盲评（{len(j)} 题）：notes 胜 {w}，负 {lo}，平 {len(j) - w - lo}（p={_mcnemar(w, lo):.3f}）；"
              f"错误条数 notes {en} / none {eo}")  # fmt: skip


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "sample":
        asyncio.run(sample(int(sys.argv[2])))
    elif len(sys.argv) == 3 and sys.argv[1] in ("run", "judge"):
        asyncio.run((run if sys.argv[1] == "run" else judge)(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] == "report":
        report()
    else:
        sys.exit(__doc__)
