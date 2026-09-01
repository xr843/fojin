"""Read what production actually served, and re-score only what the guards missed.

``run_eval`` measures citation faithfulness by *generating* 90 answers with the
LLM. That is the right instrument for a controlled before/after — the question
set is fixed, so a delta is attributable — but it costs a model call per
question and it measures a hand-curated test set rather than what users get.

This module measures production, for free. It has two halves, and keeping them
apart is the whole point:

**A. The guard-visible numbers come from ``chat_answer_diagnostics``, not from
replay.** ``chat_messages.content`` stores the answer *after* the guards ran.
``verify_quoted_content`` downgrades a non-verbatim quote by stripping its quote
marks, and its docstring is explicit that this is idempotent — "a downgraded
passage carries no quote marks, so a second pass is a no-op (and returns no
mutations — the served answer is already clean)". So replaying stored content
through the guards reports 100% grounding on every run, by construction, no
matter how bad the model was. Measured 2026-09-01 on 300 stored answers: replay
said 0 quote downgrades and 0 citation corrections; the serve-time table said
203 and 43 over the same window. The number was real; reading it as quality
would have been fiction.

The serve-time record is the raw-answer truth, because the guards wrote down
what they had to change *before* changing it. That is where faithfulness comes
from here.

**B. Replay measures the two things the guards never did.**

  - **卷号 accuracy.** ``quote_verifier._find_sources`` falls back to any
    fascicle of the cited text, so a quote that is verbatim in 卷16 passes while
    the answer says 第13卷. No guard can see this, so nothing was baked into the
    stored answer and replay against ``text_contents`` reads true.
  - **The answers the verifier declined to open.** ``verify_quoted_content``
    early-exits when the answer carries no ``【《`` marker. Those answers were
    never touched, so their stored content is raw with respect to quote
    verification — replay is the *only* way to find out what is in them. Sizing
    that cohort is what this tool exists for next.

**What this is NOT: a daily gate.** Production serves ~47.5 answers/day and
``verbatim_quote_rate``'s denominator is narrower still — roughly 25/day. At
p≈0.8 that is a standard error of ~8 points daily, ~3 weekly, ~1.5 monthly. A
daily series is noise and any threshold on it would page every day. Run it
monthly, or side-by-side around a change. The deterministic *retrieval* gate
stays daily; this does not join it.

Usage::

    # What did we actually serve over the last 30 days?
    python -m eval.replay_production --window-days 30 --tag monthly

    # Adjudicate a guard change over the same answers, before and after.
    python -m eval.replay_production --window-days 30 --tag before
    #   ...edit the guard...
    python -m eval.replay_production --ids-from eval/reports/replay-<ts>-before.json \\
        --baseline eval/reports/replay-<ts>-before.json --tag after
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.chat import ChatSource
from eval.faithfulness import (
    TRUST_STATES,
    aggregate_faithfulness,
    compute_faithfulness,
    compute_fascicle_accuracy,
)

EVAL_DIR = Path(__file__).parent
REPORTS_DIR = EVAL_DIR / "reports"

# The literal early-exit condition in ``quote_verifier.verify_quoted_content``:
# no marker → the answer is returned untouched and nothing is ever checked.
# Measured directly rather than inferred from ``citation_count`` (a slightly
# looser regex) so the coverage number means exactly "answers the verifier
# declined to look at".
CITATION_MARKER = "【《"

# ``juan_text(message_id, title, juan) -> fascicle body | None``. The message id
# is part of the key because one 经名 legitimately resolves to different texts in
# different answers — 「楞伽经」 meant two different 经 in search and in chat until
# PR #1209 — and adjudicating one answer's citation against another's fascicle
# would be worse than not adjudicating it.
JuanTextResolver = Callable[[int, str, int], "str | None"]


@dataclass(frozen=True)
class StoredAnswer:
    """One persisted assistant turn, ready to re-score."""

    message_id: int
    created_at: str
    answer: str
    sources: list[ChatSource]


@dataclass(frozen=True)
class ServeRecord:
    """What the guards recorded about an answer at serve time, pre-correction.

    This is the raw-model-quality signal. It cannot be recovered by replaying
    the stored answer, because the stored answer is the corrected one — see the
    module docstring.
    """

    message_id: int
    trust_state: str
    citation_count: int
    citation_mutations: int
    quote_mutations: int
    quote_checked: int | None


def parse_stored_sources(raw: object) -> list[ChatSource]:
    """Deserialise ``chat_messages.sources`` into ``ChatSource`` objects.

    Production writes ``[s.model_dump() for s in sources]`` (a JSON array), but
    the column is nullable and older rows predate the trilingual fields, so this
    tolerates: SQL NULL, JSON ``null``, ``[]``, and entries missing the optional
    keys. A single unparseable entry is dropped rather than raised — one bad row
    out of 1,400 must not end the run, and a row that cannot be read is a row
    whose faithfulness is genuinely unknown, not zero.
    """
    if not isinstance(raw, list):
        return []
    out: list[ChatSource] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            out.append(ChatSource(**entry))
        except Exception:
            continue
    return out


def aggregate_serve_records(records: Sequence[ServeRecord]) -> dict:
    """Fold serve-time diagnostics into the faithfulness rates.

    Mirrors ``aggregate_faithfulness``'s definitions so the two are readable
    side by side, but sourced from what the guards recorded rather than from a
    re-run. ``verbatim_quote_rate``'s denominator is answers that actually
    quoted; an answer that cites without quoting scores 0 in
    ``verified_rate_of_cited`` (it verified nothing) rather than passing
    vacuously.
    """
    if not records:
        return {}
    cited = [r for r in records if r.citation_count > 0]
    quoted = [r for r in records if (r.quote_checked or 0) > 0]
    verbatim = [r for r in quoted if r.quote_mutations == 0]
    verified = [
        r for r in cited if (r.quote_checked or 0) > 0 and not r.quote_mutations and not r.citation_mutations
    ]
    total_citations = sum(r.citation_count for r in records)
    grounded = sum(max(0, r.citation_count - r.citation_mutations) for r in records)

    distribution = dict.fromkeys(TRUST_STATES, 0)
    for r in records:
        distribution[r.trust_state] = distribution.get(r.trust_state, 0) + 1

    return {
        "num_answers": len(records),
        "citation_grounding_rate": (grounded / total_citations) if total_citations else None,
        "verified_rate_of_cited": (len(verified) / len(cited)) if cited else None,
        "verbatim_quote_rate": (len(verbatim) / len(quoted)) if quoted else None,
        "total_citations": total_citations,
        "answers_with_citations": len(cited),
        "answers_with_quotes": len(quoted),
        "answers_with_downgraded_quote": sum(1 for r in records if r.quote_mutations),
        "state_distribution": distribution,
    }


def replay_answers(
    answers: Iterable[StoredAnswer],
    juan_text: JuanTextResolver | None = None,
) -> tuple[list[dict], dict]:
    """Score stored answers with the production guards; return rows + aggregate.

    ⚠️ The grounding/verbatim rates in the returned aggregate are **tautological
    for answers the guards already corrected** — the stored text is the
    corrected text. They are meaningful only for the cohort the verifier never
    opened (``has_citation_marker == 0``) and for adjudicating a guard change
    over a fixed id set. Production faithfulness comes from
    :func:`aggregate_serve_records`. See the module docstring.

    ``fascicle_checked``/``fascicle_correct`` are exempt: no guard writes to the
    答案 based on 卷号, so replay reads true there.
    """
    rows: list[dict] = []
    for a in answers:
        row = compute_faithfulness(a.answer, a.sources)
        row["message_id"] = a.message_id
        row["created_at"] = a.created_at
        row["has_citation_marker"] = 1 if CITATION_MARKER in (a.answer or "") else 0
        row["source_count"] = len(a.sources)
        if juan_text is not None:
            row.update(compute_fascicle_accuracy(a.answer, partial(juan_text, a.message_id)))
        rows.append(row)
    return rows, aggregate_faithfulness(rows)


def coverage(rows: Sequence[dict]) -> dict:
    """How much of the run the quote verifier ever looked at."""
    marked = sum(r["has_citation_marker"] for r in rows)
    return {
        "answers": len(rows),
        "with_citation_marker": marked,
        "without_citation_marker": len(rows) - marked,
        "marker_rate": (marked / len(rows)) if rows else None,
    }


# ── DB layer (needs the prod corpus; not exercised in CI) ────────────────────


async def fetch_stored_answers(
    session,
    *,
    window_days: int = 30,
    limit: int | None = None,
    message_ids: Sequence[int] | None = None,
) -> list[StoredAnswer]:
    """Load served assistant turns, newest first.

    ``message_ids`` pins the exact set for a controlled second run and ignores
    the window entirely; without it the window selects. Rows whose sources did
    not persist are kept — an answer served with no sources is a real outcome
    (``no_sources``), and dropping it would flatter every rate.
    """
    from sqlalchemy import text as sql_text

    if message_ids is not None:
        if not message_ids:
            return []
        stmt = sql_text(
            "SELECT id, created_at, content, sources FROM chat_messages "
            "WHERE role = 'assistant' AND id = ANY(:ids) ORDER BY id"
        )
        params: dict = {"ids": list(message_ids)}
    else:
        stmt = sql_text(
            "SELECT id, created_at, content, sources FROM chat_messages "
            "WHERE role = 'assistant' AND created_at > now() - make_interval(days => :d) "
            "ORDER BY id DESC" + (" LIMIT :lim" if limit else "")
        )
        params = {"d": window_days}
        if limit:
            params["lim"] = limit

    rows = (await session.execute(stmt, params)).fetchall()
    return [
        StoredAnswer(
            message_id=r[0],
            created_at=r[1].isoformat() if r[1] else "",
            answer=r[2] or "",
            sources=parse_stored_sources(r[3]),
        )
        for r in rows
    ]


async def fetch_serve_records(session, message_ids: Sequence[int]) -> list[ServeRecord]:
    """Load the serve-time guard diagnostics for these answers.

    Answers with no diagnostics row are omitted rather than defaulted to zero —
    a missing row means the guards' verdict was never recorded, which is not the
    same as "nothing to correct".
    """
    from sqlalchemy import text as sql_text

    if not message_ids:
        return []
    rows = (
        await session.execute(
            sql_text(
                "SELECT message_id, trust_state, citation_count, citation_mutation_count, "
                "quote_mutation_count, quote_checked_count FROM chat_answer_diagnostics "
                "WHERE message_id = ANY(:ids)"
            ),
            {"ids": list(message_ids)},
        )
    ).fetchall()
    return [
        ServeRecord(
            message_id=r[0],
            trust_state=r[1],
            citation_count=r[2] or 0,
            citation_mutations=r[3] or 0,
            quote_mutations=r[4] or 0,
            quote_checked=r[5],
        )
        for r in rows
    ]


async def build_juan_resolver(session, answers: Sequence[StoredAnswer]) -> JuanTextResolver:
    """Prefetch every cited fascicle once, return a sync (message, title, juan) lookup.

    Synchronous by design: ``compute_fascicle_accuracy`` is unit-tested in CI
    where there is no database, so the metric must not learn to await. Titles
    resolve to a text_id through that answer's own retrieved sources, using the
    guard's fold rules — same source of truth the runtime used.
    """
    from sqlalchemy import text as sql_text

    from app.services.citation_guard import _norm_title
    from app.services.quote_verifier import iter_quote_citations

    body_cache: dict[tuple[int, int], str | None] = {}
    loaded: dict[tuple[int, str, int], str | None] = {}

    for a in answers:
        by_title: dict[str, int] = {}
        for s in a.sources:
            if s.title_zh and s.text_id > 0:
                by_title.setdefault(_norm_title(s.title_zh), s.text_id)
        for cite in iter_quote_citations(a.answer):
            if cite.juan is None or (a.message_id, cite.title, cite.juan) in loaded:
                continue
            text_id = by_title.get(_norm_title(cite.title))
            if text_id is None:
                # Title outside this answer's retrieved set — the guard already
                # strips those, and a fascicle cannot be adjudicated without
                # knowing its text. Unresolved → left out of the denominator.
                continue
            key = (text_id, cite.juan)
            if key not in body_cache:
                row = (
                    await session.execute(
                        sql_text(
                            "SELECT content FROM text_contents "
                            "WHERE text_id = :t AND juan_num = :j AND lang = 'lzh' LIMIT 1"
                        ),
                        {"t": text_id, "j": cite.juan},
                    )
                ).fetchone()
                body_cache[key] = row[0] if row else None
            loaded[(a.message_id, cite.title, cite.juan)] = body_cache[key]

    return lambda message_id, title, juan: loaded.get((message_id, title, juan))


# ── Reporting ────────────────────────────────────────────────────────────────


def _fmt_rate(value: object) -> str:
    return f"{round(value * 100, 1)}%" if isinstance(value, int | float) else "N/A"


def generate_report(
    rows: list[dict],
    replay_agg: dict,
    serve_agg: dict,
    cov: dict,
    *,
    selection: str,
    tag: str,
) -> str:
    lines = [
        "# 生产答案 · 引用忠实度",
        "",
        f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**选样**: {selection}",
        f"**答案数**: {cov['answers']}" + (f"  ·  **标签**: {tag}" if tag else ""),
        "",
        "> 零 LLM 调用：答案是线上已服务过的，不重新生成。",
        "",
        "## A. 忠实度（serve 时记录，原始答案上量到的）",
        "",
    ]
    if not serve_agg:
        lines += ["*该批答案没有 serve 时诊断记录。*", ""]
    else:
        lines += [
            "| 指标 | 值 | 分母 |",
            "|------|-----|------|",
            f"| `citation_grounding_rate` | {_fmt_rate(serve_agg['citation_grounding_rate'])} "
            f"| {serve_agg['total_citations']} 条引用 |",
            f"| `verified_rate_of_cited` | {_fmt_rate(serve_agg['verified_rate_of_cited'])} "
            f"| {serve_agg['answers_with_citations']} 条有引用的回答 |",
            f"| `verbatim_quote_rate` | **{_fmt_rate(serve_agg['verbatim_quote_rate'])}** "
            f"| {serve_agg['answers_with_quotes']} 条含可核验引文的回答 |",
            f"| 引文被降级的回答 | {serve_agg['answers_with_downgraded_quote']} 条 "
            f"| 共 {serve_agg['num_answers']} 条 |",
            "",
            "> **为什么这一节不从回放算。** `chat_messages.content` 存的是护栏**处理后**的答案，"
            "而 `verify_quoted_content` 把不逐字的引文降级成散文（去掉引号）后是幂等的——"
            "再跑一遍必然零改写。2026-09-01 实测 300 条：回放报 0 次降级，serve 记录是 203 次。"
            "所以原始答案的质量只能读 `chat_answer_diagnostics`，不能靠重放。",
            "",
            "### 可信状态分布（serve 时）",
            "",
            "| 状态 | 条数 |",
            "|------|------|",
        ]
        for state in TRUST_STATES:
            lines.append(f"| {state} | {serve_agg['state_distribution'].get(state, 0)} |")
        lines.append("")

    lines += [
        "## B. 回放新测：护栏看不见的部分",
        "",
        "| 指标 | 值 | 分母 |",
        "|------|-----|------|",
        f"| `fascicle_accuracy_rate`（卷号对不对） | **{_fmt_rate(replay_agg.get('fascicle_accuracy_rate'))}** "
        f"| {replay_agg.get('fascicle_checked', 0)} 条可解析卷号的引文 |",
        "",
        "> 这是唯一不查召回 chunk、直接问 `text_contents` 的指标。"
        "`quote_verifier._find_sources` 在所标卷找不到时会回退到该经**任意**卷，"
        "所以「引文逐字正确但卷号指向别处」对所有运行时护栏都是盲区——"
        "正因为没有护栏改写过它，回放在这里读到的是真值。",
        "",
        "## C. 覆盖：核验器根本没打开过的那些答案",
        "",
        f"| 全部答案 | 带 `{CITATION_MARKER}` 标记（被核验） | 无标记（**整条跳过**） |",
        "|---|---|---|",
        f"| {cov['answers']} | {cov['with_citation_marker']} "
        f"（{_fmt_rate(cov['marker_rate'])}） | {cov['without_citation_marker']} |",
        "",
        "> `verify_quoted_content` 首行即 `if \"【《\" not in answer: return answer, []`。"
        "A 节所有比率的分母**只是带标记的那部分**——无标记的那些不是「核验通过」，是「从没被看过」，"
        "而且正因为没被改写，它们的存文是**原始**的，是唯一能靠回放查清的一批。",
    ]
    return "\n".join(lines)


def compare_baseline(baseline_path: str, serve_agg: dict, replay_agg: dict, ids: Sequence[int]) -> list[str]:
    """Deltas against a prior replay report — meaningful only on the same ids."""
    try:
        prior = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    except OSError as exc:
        return ["", f"⚠️ 基线读取失败（{exc}）——本次不做对照。"]

    prior_ids = {r["message_id"] for r in prior.get("rows", [])}
    now_ids = set(ids)
    out = ["", "## 对照基线", "", f"基线：`{baseline_path}`"]
    if prior_ids and now_ids and prior_ids != now_ids:
        out += [
            "",
            f"⚠️ **两次跑的不是同一批答案**（基线 {len(prior_ids)} 条，本次 {len(now_ids)} 条，"
            f"交集 {len(prior_ids & now_ids)} 条）。差值里混着人群变化，**不可归因于代码改动**。"
            f"用 `--ids-from {baseline_path}` 重跑才能得到受控对照。",
        ]
    out += ["", "| 指标 | 基线 | 本次 | 差 |", "|---|---|---|---|"]
    pairs = [
        ("serve", "citation_grounding_rate", prior.get("serve_aggregate") or {}, serve_agg),
        ("serve", "verified_rate_of_cited", prior.get("serve_aggregate") or {}, serve_agg),
        ("serve", "verbatim_quote_rate", prior.get("serve_aggregate") or {}, serve_agg),
        ("replay", "fascicle_accuracy_rate", prior.get("replay_aggregate") or {}, replay_agg),
    ]
    for kind, key, old_agg, new_agg in pairs:
        old, new = old_agg.get(key), new_agg.get(key)
        delta = (
            f"{(new - old) * 100:+.1f}pp"
            if isinstance(old, int | float) and isinstance(new, int | float)
            else "—"
        )
        out.append(f"| `{key}` ({kind}) | {_fmt_rate(old)} | {_fmt_rate(new)} | {delta} |")
    return out


async def main() -> int:
    parser = argparse.ArgumentParser(description="Read production faithfulness; replay what the guards missed")
    parser.add_argument("--window-days", type=int, default=30, help="How far back to select answers (default 30)")
    parser.add_argument("--limit", type=int, help="Cap the number of answers")
    parser.add_argument("--ids-from", type=str,
                        help="Replay exactly the message ids in a prior report — the controlled A/B")
    parser.add_argument("--baseline", type=str, help="Prior report to diff against")
    parser.add_argument("--no-fascicle", action="store_true",
                        help="Skip the text_contents 卷号 check (saves a handful of reads per answer)")
    parser.add_argument("--tag", type=str, default="", help="Tag for the report filename")
    args = parser.parse_args()

    from app.database import async_session

    ids_filter = None
    selection = f"最近 {args.window_days} 天" + (f"（上限 {args.limit} 条）" if args.limit else "")
    if args.ids_from:
        prior = json.loads(Path(args.ids_from).read_text(encoding="utf-8"))
        ids_filter = [r["message_id"] for r in prior.get("rows", [])]
        selection = f"复现 `{args.ids_from}` 的 {len(ids_filter)} 条（受控对照）"

    async with async_session() as session:
        answers = await fetch_stored_answers(
            session, window_days=args.window_days, limit=args.limit, message_ids=ids_filter
        )
        if not answers:
            print("没有可回放的答案。")
            return 0
        ids = [a.message_id for a in answers]
        serve_records = await fetch_serve_records(session, ids)
        resolver = None if args.no_fascicle else await build_juan_resolver(session, answers)

    rows, replay_agg = replay_answers(answers, juan_text=resolver)
    serve_agg = aggregate_serve_records(serve_records)
    cov = coverage(rows)

    report = generate_report(rows, replay_agg, serve_agg, cov, selection=selection, tag=args.tag)
    if args.baseline:
        report += "\n" + "\n".join(compare_baseline(args.baseline, serve_agg, replay_agg, ids))

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag_suffix = f"-{args.tag}" if args.tag else ""
    payload = {
        "generated_at": timestamp,
        "selection": selection,
        "coverage": cov,
        "serve_aggregate": serve_agg,
        "replay_aggregate": replay_agg,
        "rows": rows,
    }
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        base = REPORTS_DIR / f"replay-{timestamp}{tag_suffix}"
        base.with_suffix(".md").write_text(report, encoding="utf-8")
        base.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = f"\nReport: {base}.md\nRaw: {base}.json"
    except OSError as exc:
        # Same trap run_eval documents: in prod eval/reports is a bind mount owned
        # by admin(1000) while the container runs as app(999). A silent fallback
        # to /tmp dies with the container, taking the ids a controlled second run
        # would need with it — so say it loudly.
        base = Path("/tmp") / f"replay-{timestamp}{tag_suffix}"
        base.with_suffix(".md").write_text(report, encoding="utf-8")
        base.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = (
            f"\n⚠️  {REPORTS_DIR} 不可写（{exc}）——报告写到了 EPHEMERAL 的 /tmp，容器重启即丢，"
            f"届时 --ids-from 无从复现。\n    修复：chgrp 999 backend/eval/reports && chmod g+w backend/eval/reports"
            f"\nReport: {base}.md\nRaw: {base}.json"
        )

    print(f"\n{'=' * 60}")
    print(report)
    print(saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
