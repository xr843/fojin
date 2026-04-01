"""Run AI Chat evaluation against the test set.

Usage:
    cd backend
    python -m eval.run_eval                       # Full evaluation
    python -m eval.run_eval --category term_explanation
    python -m eval.run_eval --limit 5
    python -m eval.run_eval --no-llm
    python -m eval.run_eval --tag baseline-v1
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
from app.services.chat import _build_llm_messages, SYSTEM_PROMPT
from app.services.rag_retrieval import retrieve_rag_context

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

    api_url, api_key, model, _ = _resolve_llm_config(None)
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
        "", "## 分类得分", "",
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

    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag_suffix = f"-{args.tag}" if args.tag else ""
    report_path = REPORTS_DIR / f"eval-{timestamp}{tag_suffix}.md"
    report_path.write_text(report, encoding="utf-8")

    raw_path = REPORTS_DIR / f"eval-{timestamp}{tag_suffix}.json"
    raw_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(report)
    print(f"\nReport: {report_path}")
    print(f"Raw: {raw_path}")


if __name__ == "__main__":
    asyncio.run(main())
