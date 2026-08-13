"""Run AI Chat evaluation against the test set.

Usage:
    cd backend
    python -m eval.run_eval                       # Full evaluation
    python -m eval.run_eval --category term_explanation
    python -m eval.run_eval --limit 5
    python -m eval.run_eval --no-llm
    python -m eval.run_eval --tag baseline-v1

    # Regression gate (run where the corpus DB is reachable, e.g. prod/cron):
    python -m eval.run_eval --no-llm --baseline eval/reports/<prev>.json \
        --fail-on-regression --regression-tolerance 0.02
    python -m eval.run_eval --no-llm --min-recall5 0.70
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text as sql_text

from app.config import settings
from app.database import async_session
from app.services.chat import _build_llm_messages
from app.services.citation_guard import _norm_title
from app.services.llm_client import _with_reasoning_headroom, configured_thinking_params
from app.services.quote_verifier import iter_quote_citations
from app.services.rag_retrieval import retrieve_rag_context
from eval.faithfulness import (
    TRUST_STATES,
    aggregate_faithfulness,
    compute_faithfulness,
    compute_fascicle_accuracy,
    detect_faithfulness_regressions,
)
from eval.retrieval_metrics import (
    aggregate,
    aggregate_by_type,
    compute_metrics_graded,
    detect_regressions,
    sources_to_pairs,
)
from eval.scorer import score_out_of_scope, score_with_llm_judge

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
TEST_SET_PATH = EVAL_DIR / "test_set.json"
REPORTS_DIR = EVAL_DIR / "reports"

# 重推理模型（deepseek-v4*）单题实测总耗时 91.9s / 197.8s，60 秒会让整份报告
# 变成 90 条 [ERROR]。300 秒留足余量，反正 eval 是离线跑的，慢不要紧、错才要紧。
EVAL_LLM_TIMEOUT_S = 300

# eval 的答案预算与生产同口径（生产是 2000，reader 模式 8000）。
_EVAL_ANSWER_TOKENS = 2000


def build_eval_llm_body(model: str, messages: list[dict], temperature: float) -> dict:
    """eval 调用 LLM 的请求体 —— 独立成函数是为了能被单测钉住。

    2026-08-13 在生产机上照抄改动前的参数实跑（真实提示词、deepseek-v4-pro）：
    ``timeout=60, max_tokens=2000`` → 30.2 秒后拿到 **正文 0 字**、推理 2,686 字、
    ``finish=length``。推理与可见答案共用同一个 max_tokens，2000 全被推理吃掉，
    与 #1095 修的生产故障同源，只是这次躲在 eval 里 —— 而 eval 不会报错，它会
    安静地产出一份「90 道题全空」的报告，然后我们拿它去比较档位。
    """
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": _with_reasoning_headroom(model, _EVAL_ANSWER_TOKENS),
        # 让 eval 能按 CHAT_REASONING_EFFORT 跑不同档位，否则 high / low 的
        # 引用准确性没法对比 —— 而那正是换默认档的唯一依据。
        **configured_thinking_params(model),
    }


def load_test_set() -> dict:
    with open(TEST_SET_PATH, encoding="utf-8") as f:
        return json.load(f)



# ── 卷级引文准确率：拿 text_contents 当独立真源 ─────────────────────────
#
# 其余忠实度指标重放的是运行时护栏，而护栏看不见「引错卷」——quote_verifier 在
# 所标卷无匹配时会回退到该经任意卷。所以这里绕开 chunk，直接问该卷正文。
#
# 经名 → text_id 沿用护栏的繁简折叠规则，从本题召回的来源里解析：与运行时同源，
# 也省掉再建一份标题索引。查不到的引用不计入分母（见 compute_fascicle_accuracy）。
_JUAN_TEXT_CACHE: dict[tuple[int, int], str | None] = {}


async def _prefetch_cited_fascicles(session, answer: str, sources: list):
    """Load the fascicles this answer cites and return a sync lookup over them.

    Prefetched rather than fetched on demand so ``compute_fascicle_accuracy``
    stays pure and synchronous — the metric is unit-tested in CI, where there is
    no database, and threading an async callable through it would end that.

    Only the (title, juan) pairs the answer actually cites are loaded, so a run
    costs a handful of primary-key reads per question, cached across questions.
    """
    by_title: dict[str, int] = {}
    for s in sources:
        if getattr(s, "title_zh", None) and getattr(s, "text_id", 0) > 0:
            by_title.setdefault(_norm_title(s.title_zh), s.text_id)

    loaded: dict[tuple[str, int], str | None] = {}
    for cite in iter_quote_citations(answer):
        if cite.juan is None or (cite.title, cite.juan) in loaded:
            continue
        text_id = by_title.get(_norm_title(cite.title))
        if text_id is None:
            # Title outside the retrieved set — citation_guard already strips
            # those, and we cannot adjudicate a fascicle without knowing which
            # text it belongs to. Left unresolved → excluded from the denominator.
            continue
        key = (text_id, cite.juan)
        if key not in _JUAN_TEXT_CACHE:
            row = (
                await session.execute(
                    sql_text(
                        "SELECT content FROM text_contents "
                        "WHERE text_id = :t AND juan_num = :j AND lang = 'lzh' LIMIT 1"
                    ),
                    {"t": text_id, "j": cite.juan},
                )
            ).fetchone()
            _JUAN_TEXT_CACHE[key] = row[0] if row else None
        loaded[(cite.title, cite.juan)] = _JUAN_TEXT_CACHE[key]

    return lambda title, juan: loaded.get((title, juan))


async def run_single_question(
    question_data: dict, skip_llm: bool = False, temperature: float = 0.7,
    test_set_version: str | None = None,
) -> dict:
    """Run a single question through the RAG + LLM pipeline and score it."""
    qid = question_data["id"]
    question = question_data["question"]
    category = question_data["category"]
    t0 = time.monotonic()

    result = {
        "id": qid,
        "category": category,
        "question": question,
        "difficulty": question_data.get("difficulty", "medium"),
        # Stamped per row (the report JSON is a flat list, so there is no header
        # to put it in) — lets a later run detect that a stored baseline was
        # measured with a different ruler. See baseline_version_mismatch.
        "test_set_version": test_set_version,
    }

    # Step 1: RAG retrieval
    async with async_session() as session:
        sources, context_text = await retrieve_rag_context(session, question)

    result["num_sources"] = len(sources)
    result["source_titles"] = [s.title_zh for s in sources if s.title_zh]
    result["context_length"] = len(context_text)
    # Deterministic retrieval metrics (Recall@K/Hit@K/MRR/Precision@K). Needs no
    # LLM, so this is populated even in --no-llm mode.
    # Strict (relevance>=2) keeps the original key names so stored baselines keep
    # comparing like for like; the lenient family and retrieval_type ride along.
    result["retrieval_metrics"] = compute_metrics_graded(
        sources_to_pairs(sources), question_data
    )
    retrieval_time = time.monotonic() - t0

    if skip_llm:
        result["answer"] = "(skipped)"
        result["scores"] = {
            "retrieval_relevance": -1, "citation_accuracy": -1,
            "answer_completeness": -1, "no_hallucination": -1,
            "reason": "LLM skipped",
        }
        result["timing"] = {"retrieval_s": round(retrieval_time, 2), "llm_s": 0, "total_s": round(retrieval_time, 2)}
        return result

    # Step 2: LLM generation
    import httpx

    from app.services.chat import _resolve_llm_config

    api_url, api_key, model, _, _ = _resolve_llm_config(None)
    llm_messages = _build_llm_messages([], context_text, question)

    t1 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=EVAL_LLM_TIMEOUT_S) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=build_eval_llm_body(model, llm_messages, temperature),
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        answer = f"[ERROR] {exc}"
    llm_time = time.monotonic() - t1

    result["answer"] = answer
    result["model"] = model

    # Deterministic citation-faithfulness: replay the production trust pipeline
    # (citation guard → quote verifier → trust status) over the raw answer. Needs
    # the answer, so it is populated only on LLM-on runs and skipped for errored
    # generations (which carry no citations and would drag the rates down).
    if not answer.startswith("[ERROR]"):
        result["faithfulness"] = compute_faithfulness(answer, sources)
        # 卷级引文准确率：与上面那行不同，它绕开召回的 chunk，直接问 text_contents
        # 「这段引文在所标的那一卷里吗」——护栏看不见的正是这一类错误。
        async with async_session() as fascicle_session:
            juan_text = await _prefetch_cited_fascicles(fascicle_session, answer, sources)
        result["faithfulness"].update(compute_fascicle_accuracy(answer, juan_text))

    # Step 3: Scoring
    if category == "out_of_scope":
        result["scores"] = score_out_of_scope(answer, question_data.get("expected_behavior", "refuse"))
    else:
        result["scores"] = await score_with_llm_judge(
            question=question,
            answer=answer,
            reference_points=question_data.get("reference_answer_points", []),
            reference_sources=question_data.get("reference_sources", []),
            retrieved_chunks=context_text,
        )

    result["timing"] = {
        "retrieval_s": round(retrieval_time, 2),
        "llm_s": round(llm_time, 2),
        "total_s": round(time.monotonic() - t0, 2),
    }
    return result


def _fmt_rate(value: object) -> str:
    """Percent string for a 0..1 rate, or 'N/A' when the rate is unmeasured."""
    return f"{round(value * 100, 1)}%" if isinstance(value, int | float) else "N/A"


_TYPE_NAMES = {
    "attribution": "归属题（出处/位置，查表问题）",
    "passage": "段落题（义理/内容，相似度问题）",
    "unspecified": "⚠️ 未标注题型",
    "advisory": "无典可依（只评答案质量）",
}


def _retrieval_type_section(results: list[dict]) -> list[str]:
    """Retrieval metrics split by 归属题 / 段落题.

    The two are answered by different mechanisms — attribution is a lookup,
    passage is a similarity search — so a single pooled Recall@5 hides which one
    is failing. Buckets carry their question count so a 10-question bucket isn't
    read as a stable rate.
    """
    by_type = aggregate_by_type([r["retrieval_metrics"] for r in results if r.get("retrieval_metrics")])
    if not by_type:
        return []
    lines = [
        "", "### 按题型拆分", "",
        "| 题型 | 题数 | Recall@5 严格 | Recall@5 宽松 | Hit@5 严格 | MRR |",
        "|------|------|------|------|------|------|",
    ]
    for key in ("attribution", "passage", "unspecified", "advisory"):
        bucket = by_type.get(key)
        if not bucket:
            continue
        if key == "advisory":
            lines.append(f"| {_TYPE_NAMES[key]} | {bucket['n']} | — | — | — | — |")
            continue
        lines.append(
            f"| {_TYPE_NAMES[key]} | {bucket['n']} "
            f"| {round(bucket.get('recall@5', 0), 3)} "
            f"| {round(bucket.get('lenient_recall@5', 0), 3)} "
            f"| {round(bucket.get('hit@5', 0), 3)} "
            f"| {round(bucket.get('mrr', 0), 3)} |"
        )
    if "unspecified" in by_type:
        lines += ["", "*⚠️ 有题目未标注 retrieval_type，请补 test_set.json 的 `retrieval_type` 字段。*"]
    return lines


def _faithfulness_section(faith_agg: dict) -> list[str]:
    """Render the deterministic citation-faithfulness block as report lines.

    Empty ``faith_agg`` (a ``--no-llm`` retrieval-only run generates no answers
    to check) returns an explanatory note instead of misleading zeros.
    """
    if not faith_agg:
        return [
            "", "## 引用忠实度（确定性 / 每一句可点回原典）", "",
            "*本次为 --no-llm 检索评测，未生成回答，故无忠实度数据。*", "",
        ]

    state_names = {
        "verified": "已核验",
        "sources_available": "有来源未引用",
        "citation_corrected": "引用被纠正",
        "quote_relaxed": "引文已转述（降级）",
        "quote_unverified": "引文未核实（旧）",
        "no_sources": "无来源",
    }
    dist = faith_agg.get("state_distribution", {})
    lines = [
        "", "## 引用忠实度（确定性 / 每一句可点回原典）", "",
        f"*基于 {faith_agg.get('num_answers', 0)} 道生成回答，重放线上"
        "「引用守卫 → 引文核验 → 可信状态」管线*", "",
        "| 指标 | 值 | 分母 |", "|------|-----|------|",
        f"| 引用可核验率 (citation_grounding_rate) | {_fmt_rate(faith_agg.get('citation_grounding_rate'))} "
        f"| {faith_agg.get('total_citations', 0)} 条引用 |",
        f"| **服务可信率 (served_trustworthy_rate)** | **{_fmt_rate(faith_agg.get('served_trustworthy_rate'))}** "
        f"| {faith_agg.get('answers_with_citations', 0)} 条有引用回答 |",
        f"| 完全核验率·严格 (verified_rate_of_cited) | {_fmt_rate(faith_agg.get('verified_rate_of_cited'))} "
        f"| {faith_agg.get('answers_with_citations', 0)} 条有引用回答 |",
        f"| **逐字引用保真度 (verbatim_quote_rate)** | **{_fmt_rate(faith_agg.get('verbatim_quote_rate'))}** "
        f"| {faith_agg.get('answers_with_quotes', 0)} 条含可核验引文的回答 |",
        f"| **卷号准确率 (fascicle_accuracy_rate)** | **{_fmt_rate(faith_agg.get('fascicle_accuracy_rate'))}** "
        f"| {faith_agg.get('fascicle_checked', 0)} 条可判定引文 |",
        f"| 含转述降级引文的回答数 | {faith_agg.get('answers_with_downgraded_quote', 0)} | — |",
        "",
        "> `verified_rate_of_cited` 的分母是**有引用**的回答:引用了来源却一个字都不引原文的",
        "> 回答记 0,不记 1 —— 它什么都没核验。`verbatim_quote_rate` 的分母是**真的引用了",
        "> 原文**的回答,回答「模型把原典放进引号里时,有多少次是逐字的」。两者独立移动,",
        "> 所以一次 run 无法靠少引用来刷分。",
        "",
        "> `fascicle_accuracy_rate` 是唯一不查召回 chunk、而是直接问 `text_contents`",
        "> 「这段引文在所标的那一卷里吗」的指标。其余各项都重放运行时护栏,而护栏看不见",
        "> 引错卷 —— quote_verifier 在所标卷无匹配时会回退到该经任意卷,于是引文在卷十六",
        "> 被找到、答案却标第13卷,两道防线一起放行(2026-07-29 线上原形)。分母只计",
        "> **能判定**的引文:经名不在召回集、或查不到该卷正文的,不计入,不静默记错。",
        "",
        "**可信状态分布**", "",
        "| 状态 | 数量 |", "|------|------|",
    ]
    lines += [f"| {state_names.get(s, s)} | {dist.get(s, 0)} |" for s in TRUST_STATES]
    lines.append("")
    return lines


def generate_report(results: list[dict], tag: str = "") -> str:
    """Generate a Markdown report from evaluation results."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(results)

    categories: dict[str, dict] = {}
    all_scores: dict[str, list] = {
        "retrieval_relevance": [], "citation_accuracy": [],
        "answer_completeness": [], "no_hallucination": [],
    }

    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {
                "retrieval_relevance": [], "citation_accuracy": [],
                "answer_completeness": [], "no_hallucination": [], "count": 0,
            }
        categories[cat]["count"] += 1
        for dim in all_scores:
            val = r["scores"].get(dim, -1)
            if val >= 0:
                categories[cat][dim].append(val)
                all_scores[dim].append(val)

    def avg(lst: list) -> float:
        return round(sum(lst) / len(lst), 2) if lst else 0

    overall = (
        avg(all_scores["retrieval_relevance"])
        + avg(all_scores["citation_accuracy"])
        + avg(all_scores["answer_completeness"])
        + avg(all_scores["no_hallucination"]) * 3
    )
    overall_pct = round(overall / 12 * 100, 1)

    # Deterministic retrieval metrics (no LLM judge involved).
    retr_agg = aggregate([r["retrieval_metrics"] for r in results if r.get("retrieval_metrics")])
    graded = sum(
        1 for r in results
        if r.get("retrieval_metrics", {}).get("num_gold", 0) > 0
    )

    # Deterministic citation-faithfulness (replays the runtime trust pipeline).
    faith_agg = aggregate_faithfulness([r.get("faithfulness") for r in results])

    cat_names = {
        "term_explanation": "名相解释", "source_lookup": "经文出处",
        "historical": "人物历史", "comparative": "义理比较",
        "practice": "修行实践", "out_of_scope": "超出范围",
    }

    lines = [
        f"# AI Chat 评测报告{' — ' + tag if tag else ''}",
        "", f"**日期**: {now}", f"**题目数**: {total}",
        f"**模型**: {results[0].get('model', 'unknown') if results else 'N/A'}",
        f"**综合得分**: {overall_pct}%",
        "", "## 总体评分", "",
        "| 维度 | 平均分 | 满分 |", "|------|--------|------|",
        f"| 检索相关性 | {avg(all_scores['retrieval_relevance'])} | 3 |",
        f"| 引用准确性 | {avg(all_scores['citation_accuracy'])} | 3 |",
        f"| 回答完整性 | {avg(all_scores['answer_completeness'])} | 3 |",
        f"| 无编造 | {avg(all_scores['no_hallucination'])} | 1 |",
        "", "## 检索指标（确定性，对照黄金来源）", "",
        f"*基于 {graded}/{total} 道有黄金来源标注的题目*",
        "",
        "*严格 = 只认 relevance≥2 的正解；宽松 = 同时认 relevance=1 的等价可接受来源。"
        "两者差值就是「检索找到了站得住的出处，只是不是那一部」的量。*",
        "",
        "| 指标 | 严格 | 宽松 |", "|------|------|------|",
        f"| Recall@1 | {round(retr_agg.get('recall@1', 0), 3)} | "
        f"{round(retr_agg.get('lenient_recall@1', 0), 3)} |",
        f"| Recall@3 | {round(retr_agg.get('recall@3', 0), 3)} | "
        f"{round(retr_agg.get('lenient_recall@3', 0), 3)} |",
        f"| Recall@5 | {round(retr_agg.get('recall@5', 0), 3)} | "
        f"{round(retr_agg.get('lenient_recall@5', 0), 3)} |",
        f"| Hit@5 | {round(retr_agg.get('hit@5', 0), 3)} | "
        f"{round(retr_agg.get('lenient_hit@5', 0), 3)} |",
        f"| MRR | {round(retr_agg.get('mrr', 0), 3)} | "
        f"{round(retr_agg.get('lenient_mrr', 0), 3)} |",
        f"| Precision@5 | {round(retr_agg.get('precision@5', 0), 3)} | "
        f"{round(retr_agg.get('lenient_precision@5', 0), 3)} |",
    ]

    lines += _retrieval_type_section(results)

    lines += _faithfulness_section(faith_agg)

    lines += [
        "## 分类得分", "",
        "| 分类 | 题数 | 检索 | 引用 | 完整 | 无编造 |",
        "|------|------|------|------|------|--------|",
    ]

    for cat in ["term_explanation", "source_lookup", "historical", "comparative", "practice", "out_of_scope"]:
        if cat in categories:
            c = categories[cat]
            lines.append(
                f"| {cat_names.get(cat, cat)} | {c['count']} "
                f"| {avg(c['retrieval_relevance'])} | {avg(c['citation_accuracy'])} "
                f"| {avg(c['answer_completeness'])} | {avg(c['no_hallucination'])} |"
            )

    total_time = sum(r.get("timing", {}).get("total_s", 0) for r in results)
    avg_time = round(total_time / total, 1) if total else 0

    lines += [
        "", "## 性能", "",
        f"- 平均耗时: {avg_time}s/题",
        f"- 总耗时: {round(total_time, 1)}s",
        "", "## 低分题目（完整性 <= 1）", "",
    ]

    low_scores = [
        r for r in results
        if 0 <= r["scores"].get("answer_completeness", 3) <= 1
    ]
    if low_scores:
        for r in low_scores:
            lines.append(f"- **{r['id']}** ({cat_names.get(r['category'], r['category'])}): {r['question']}")
            s = r["scores"]
            lines.append(f"  - 评分: 检索={s['retrieval_relevance']} 引用={s['citation_accuracy']} 完整={s['answer_completeness']} 无编造={s['no_hallucination']}")
            lines.append(f"  - 原因: {s.get('reason', '')}")
            lines.append("")
    else:
        lines.append("无")

    return "\n".join(lines)


def baseline_version_mismatch(
    baseline_results: list[dict], current_version: str | None
) -> str | None:
    """Message when the baseline was measured with a different test-set version.

    Changing the gold set changes what the numbers MEAN — after the v1.2→v1.3
    ruler rebuild (11 more graded questions, 112 equivalent sources, some gold
    re-graded) a v1.2 baseline and a v1.3 run are simply different measurements,
    and comparing them manufactures phantom regressions. Detected rather than
    silently tolerated; the caller decides whether to warn or fail.
    """
    baseline_versions = {
        r.get("test_set_version") for r in baseline_results if r.get("test_set_version")
    }
    if not baseline_versions:
        baseline_versions = {"(未标注，v1.2 或更早)"}
    if current_version and baseline_versions != {current_version}:
        return (
            f"baseline 的测试集版本 {sorted(baseline_versions)} 与本次 {current_version} 不一致 —— "
            "口径已变，指标不可直接对比。请用新版重新生成 baseline："
            "python -m eval.run_eval --no-llm --tag baseline"
        )
    return None


def compare_baseline(
    baseline_path: str,
    current_agg: dict,
    current_faith: dict,
    tolerance: float = 0.02,
    current_version: str | None = None,
) -> tuple[list[str], str | None]:
    """Compare this run against a prior raw eval JSON.

    Returns ``(regressions, error)``. ``error`` is a message when the baseline
    could not be read or parsed — a state the caller must not confuse with "no
    regressions found", which is why the two are separate return values rather
    than an empty list. Extracted from ``main`` so the distinction is testable
    without a corpus DB.

    A test-set version mismatch is reported through ``error`` too: comparing
    across ruler versions is not a meaningful "no regressions" answer either.
    """
    try:
        baseline_results = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
        mismatch = baseline_version_mismatch(baseline_results, current_version)
        if mismatch:
            return [], mismatch
        baseline_agg = aggregate(
            [r["retrieval_metrics"] for r in baseline_results if r.get("retrieval_metrics")]
        )
        regressions = detect_regressions(current_agg, baseline_agg, tolerance)
        # Faithfulness regressions only when BOTH runs generated answers —
        # a --no-llm baseline or current run has no rates to compare.
        baseline_faith = aggregate_faithfulness(
            [r.get("faithfulness") for r in baseline_results]
        )
        if current_faith and baseline_faith:
            regressions += detect_faithfulness_regressions(
                current_faith, baseline_faith, tolerance
            )
        return regressions, None
    except (OSError, ValueError, KeyError) as exc:
        return [], str(exc)


async def main():
    parser = argparse.ArgumentParser(description="Run AI Chat evaluation")
    parser.add_argument("--category", type=str, help="Only run questions from this category")
    parser.add_argument("--limit", type=int, help="Limit number of questions")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM, only test RAG retrieval")
    parser.add_argument("--temperature", type=float, default=0.7,
                        help="LLM sampling temperature. Use 0 for a deterministic, reproducible "
                             "run when measuring a faithfulness delta (default 0.7 matches prod chat)")
    parser.add_argument("--tag", type=str, default="", help="Tag for the report")
    parser.add_argument("--baseline", type=str, help="Prior raw eval JSON to compare retrieval metrics against")
    parser.add_argument("--fail-on-regression", action="store_true",
                        help="Exit non-zero if retrieval metrics regress vs --baseline")
    parser.add_argument("--regression-tolerance", type=float, default=0.02,
                        help="Allowed drop before a metric counts as a regression (default 0.02)")
    parser.add_argument("--min-recall5", type=float,
                        help="Exit non-zero if mean Recall@5 falls below this absolute floor")
    parser.add_argument("--min-citation-grounding", type=float,
                        help="Exit non-zero if citation_grounding_rate falls below this floor "
                             "(LLM-on runs only — needs generated answers)")
    parser.add_argument("--min-verified-rate", type=float,
                        help="Exit non-zero if verified_rate_of_cited falls below this floor "
                             "(LLM-on runs only — needs generated answers)")
    args = parser.parse_args()

    test_set = load_test_set()
    questions = test_set["questions"]

    if args.category:
        questions = [q for q in questions if q["category"] == args.category]
        print(f"Filtered to {len(questions)} questions in category: {args.category}")

    if args.limit:
        questions = questions[:args.limit]
        print(f"Limited to {args.limit} questions")

    print(f"\nRunning evaluation on {len(questions)} questions...")
    print(f"Model: {settings.llm_model or 'auto-detect'}")
    print(f"LLM generation: {'OFF' if args.no_llm else 'ON'}\n")

    results = []
    for i, q in enumerate(questions):
        print(f"  [{i+1}/{len(questions)}] {q['id']}: {q['question'][:40]}...", end="", flush=True)
        try:
            result = await run_single_question(
                q, skip_llm=args.no_llm, temperature=args.temperature,
                test_set_version=test_set.get("version"),
            )
            results.append(result)
            score = result["scores"]
            t = result["timing"]["total_s"]
            if score.get("answer_completeness", -1) >= 0:
                print(f" done ({score['answer_completeness']}/3, {t}s)")
            else:
                print(f" skipped ({t}s)")
        except Exception as exc:
            print(f" ERROR: {exc}")
            results.append({
                "id": q["id"], "category": q["category"], "question": q["question"],
                "answer": f"[ERROR] {exc}", "scores": {}, "timing": {"total_s": 0},
            })

    report = generate_report(results, tag=args.tag)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag_suffix = f"-{args.tag}" if args.tag else ""

    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / f"eval-{timestamp}{tag_suffix}.md"
        report_path.write_text(report, encoding="utf-8")
        raw_path = REPORTS_DIR / f"eval-{timestamp}{tag_suffix}.json"
        raw_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = f"\nReport: {report_path}\nRaw: {raw_path}"
    except OSError as exc:
        # Fallback: /tmp is ephemeral — it dies with the container, taking the
        # run's raw JSON (and thus any future --baseline) with it. In prod
        # ``eval/reports`` is a bind mount of ``backend/eval/reports`` on the
        # host, owned by admin(1000) while the container runs as app(999), so an
        # unwritable dir silently downgraded every report to a temp file. Say so.
        fallback = Path("/tmp")
        report_path = fallback / f"eval-{timestamp}{tag_suffix}.md"
        report_path.write_text(report, encoding="utf-8")
        raw_path = fallback / f"eval-{timestamp}{tag_suffix}.json"
        raw_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = (
            f"\n⚠️  {REPORTS_DIR} 不可写（{exc}）——报告写到了 EPHEMERAL 的 /tmp，"
            f"容器重启即丢失。\n    修复：chgrp 999 backend/eval/reports && chmod g+w backend/eval/reports"
            f"\nReport: {report_path}\nRaw: {raw_path}"
        )

    print(f"\n{'='*60}")
    print(report)
    print(saved)

    # Regression gate: usable wherever the corpus DB is reachable (e.g. prod cron).
    current_agg = aggregate([r["retrieval_metrics"] for r in results if r.get("retrieval_metrics")])
    current_faith = aggregate_faithfulness([r.get("faithfulness") for r in results])
    gate_failed = False

    if args.baseline:
        regressions, error = compare_baseline(
            args.baseline, current_agg, current_faith, args.regression_tolerance,
            current_version=test_set.get("version"),
        )
        print(f"\n{'='*60}\n回归检查（对照 {args.baseline}）：")
        if error is not None:
            # A baseline we could not read is not a baseline we passed. Falling
            # through here left gate_failed False, so --fail-on-regression exited
            # 0 on a corrupt or missing file — the gate silently stopped gating.
            print(f"  ⚠️  [baseline 对照失败] {error}")
            if args.fail_on_regression:
                gate_failed = True
        elif regressions:
            for reg in regressions:
                print(f"  ⚠️  {reg}")
            if args.fail_on_regression:
                gate_failed = True
        else:
            print("  ✓ 检索/忠实度指标无回归")

    if args.min_recall5 is not None:
        recall5 = current_agg.get("recall@5")
        if recall5 is None or recall5 < args.min_recall5:
            print(f"\n  ⚠️  Recall@5 {recall5} 低于下限 {args.min_recall5}")
            gate_failed = True

    # Faithfulness floors. current_faith is empty on --no-llm runs; treat a
    # requested floor with no data to check as a failure so a misconfigured
    # gate (floor set but LLM off) is loud rather than silently passing.
    for flag_val, key, label in (
        (args.min_citation_grounding, "citation_grounding_rate", "引用可核验率"),
        (args.min_verified_rate, "verified_rate_of_cited", "有引用回答完全核验率"),
    ):
        if flag_val is None:
            continue
        rate = current_faith.get(key)
        if rate is None or rate < flag_val:
            shown = f"{rate:.3f}" if isinstance(rate, int | float) else "N/A（本次未生成回答）"
            print(f"\n  ⚠️  {label} {shown} 低于下限 {flag_val}")
            gate_failed = True

    if gate_failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
