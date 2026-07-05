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

from app.config import settings
from app.database import async_session
from app.services.chat import _build_llm_messages
from app.services.rag_retrieval import retrieve_rag_context
from eval.faithfulness import (
    TRUST_STATES,
    aggregate_faithfulness,
    compute_faithfulness,
    detect_faithfulness_regressions,
)
from eval.retrieval_metrics import (
    aggregate,
    compute_metrics,
    detect_regressions,
    gold_entries,
    sources_to_pairs,
)
from eval.scorer import score_out_of_scope, score_with_llm_judge

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
TEST_SET_PATH = EVAL_DIR / "test_set.json"
REPORTS_DIR = EVAL_DIR / "reports"


def load_test_set() -> dict:
    with open(TEST_SET_PATH, encoding="utf-8") as f:
        return json.load(f)


async def run_single_question(question_data: dict, skip_llm: bool = False) -> dict:
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
    }

    # Step 1: RAG retrieval
    async with async_session() as session:
        sources, context_text = await retrieve_rag_context(session, question)

    result["num_sources"] = len(sources)
    result["source_titles"] = [s.title_zh for s in sources if s.title_zh]
    result["context_length"] = len(context_text)
    # Deterministic retrieval metrics (Recall@K/Hit@K/MRR/Precision@K). Needs no
    # LLM, so this is populated even in --no-llm mode.
    result["retrieval_metrics"] = compute_metrics(
        sources_to_pairs(sources), gold_entries(question_data)
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
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": llm_messages, "temperature": 0.7, "max_tokens": 2000},
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
        "quote_unverified": "引文未核实",
        "no_sources": "无来源",
    }
    dist = faith_agg.get("state_distribution", {})
    lines = [
        "", "## 引用忠实度（确定性 / 每一句可点回原典）", "",
        f"*基于 {faith_agg.get('num_answers', 0)} 道生成回答，重放线上"
        "「引用守卫 → 引文核验 → 可信状态」管线*", "",
        "| 指标 | 值 |", "|------|-----|",
        f"| 引用可核验率 (citation_grounding_rate) | {_fmt_rate(faith_agg.get('citation_grounding_rate'))} |",
        f"| 有引用回答的完全核验率 (verified_rate_of_cited) | {_fmt_rate(faith_agg.get('verified_rate_of_cited'))} |",
        f"| 含未核实引文的回答数 | {faith_agg.get('answers_with_unverified_quote', 0)} |",
        f"| 引用总数 / 有引用回答数 | {faith_agg.get('total_citations', 0)} / {faith_agg.get('answers_with_citations', 0)} |",
        "", "**可信状态分布**", "",
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
        f"*基于 {graded}/{total} 道有黄金来源标注的题目*", "",
        "| 指标 | 值 |", "|------|-----|",
        f"| Recall@1 | {round(retr_agg.get('recall@1', 0), 3)} |",
        f"| Recall@3 | {round(retr_agg.get('recall@3', 0), 3)} |",
        f"| Recall@5 | {round(retr_agg.get('recall@5', 0), 3)} |",
        f"| Hit@5 | {round(retr_agg.get('hit@5', 0), 3)} |",
        f"| MRR | {round(retr_agg.get('mrr', 0), 3)} |",
        f"| Precision@5 | {round(retr_agg.get('precision@5', 0), 3)} |",
    ]

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


async def main():
    parser = argparse.ArgumentParser(description="Run AI Chat evaluation")
    parser.add_argument("--category", type=str, help="Only run questions from this category")
    parser.add_argument("--limit", type=int, help="Limit number of questions")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM, only test RAG retrieval")
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
            result = await run_single_question(q, skip_llm=args.no_llm)
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
    except OSError:
        # Fallback: write to /tmp when running inside Docker
        fallback = Path("/tmp")
        report_path = fallback / f"eval-{timestamp}{tag_suffix}.md"
        report_path.write_text(report, encoding="utf-8")
        raw_path = fallback / f"eval-{timestamp}{tag_suffix}.json"
        raw_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = f"\nReport: {report_path}\nRaw: {raw_path}"

    print(f"\n{'='*60}")
    print(report)
    print(saved)

    # Regression gate: usable wherever the corpus DB is reachable (e.g. prod cron).
    current_agg = aggregate([r["retrieval_metrics"] for r in results if r.get("retrieval_metrics")])
    current_faith = aggregate_faithfulness([r.get("faithfulness") for r in results])
    gate_failed = False

    if args.baseline:
        try:
            baseline_results = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
            baseline_agg = aggregate(
                [r["retrieval_metrics"] for r in baseline_results if r.get("retrieval_metrics")]
            )
            regressions = detect_regressions(current_agg, baseline_agg, args.regression_tolerance)
            # Faithfulness regressions only when BOTH runs generated answers —
            # a --no-llm baseline or current run has no rates to compare.
            baseline_faith = aggregate_faithfulness(
                [r.get("faithfulness") for r in baseline_results]
            )
            if current_faith and baseline_faith:
                regressions += detect_faithfulness_regressions(
                    current_faith, baseline_faith, args.regression_tolerance
                )
            print(f"\n{'='*60}\n回归检查（对照 {args.baseline}）：")
            if regressions:
                for reg in regressions:
                    print(f"  ⚠️  {reg}")
                if args.fail_on_regression:
                    gate_failed = True
            else:
                print("  ✓ 检索/忠实度指标无回归")
        except (OSError, ValueError, KeyError) as exc:
            print(f"\n[baseline 对照失败] {exc}")

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
