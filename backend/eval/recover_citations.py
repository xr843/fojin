"""Can we name the 出处 of canon the model quoted from memory but never cited?

Measured over 30 days of production (2026-09-01/02): of 1,441 served answers,
**461 carry no ``【《经名》第N卷】`` marker at all**, so ``verify_quoted_content``
early-exits and never examines them. Inside that cohort **229 quoted passages
across 109 answers are verbatim canon** that was *not* in that answer's
retrieved chunks — the model recalled them from its parameters, so fojin could
not verify them at serve time and served them with no clickable source.

That is the product's promise (每一句都能点回原典) leaking on ~7.6% of answers,
and it is downstream of retrieval recall rather than of the guards: the
retriever did not surface the passage, the model knew it anyway.

**Verdict (2026-09-02): do not auto-attach recovered citations wholesale.**

===================================  =======  ===================================
measurement                          value    consequence
===================================  =======  ===================================
recovery — quotes given any 出处     26.7%    three quarters stay unattributable
of those, unique to one text         49.8%    the median passage matches 2 texts
precision, **unique** resolutions    96.3%    the only shippable subset
precision, ambiguous resolutions     40.0%    unusable
===================================  =======  ===================================

The pooled precision reads 81% and describes neither population — reporting it
alone would have hidden the one fact that decides the question. The ambiguous
bucket fails for a systematic reason, not a random one: the resolver prefers
root canon while the model had cited a 注疏 that also contains the words
(《地藏本願經科註》 vs 《地藏菩薩本願經》). The resolver is often the *better*
attribution there — but it is overruling an attribution the runtime guard
already verified, which is not a trade to make silently.

So a safe subset exists and is identifiable in advance (``unique_text``), worth
roughly 114 passages a month at 96.3%. Whether even that ships is a product
call, not this module's: these answers currently carry *no* citation, and
[[answer-fidelity-is-the-bar]] is explicit that a clickable-but-misplaced
citation is worse than none — so a 1-in-27 error rate argues for presenting a
recovery as a lead ("疑似出自…") rather than as a verified citation.

**Method, and why this exact shape.** Three earlier attempts were discarded
because their control arms failed, and the control arm is the point:

===========================================  ==========  ====================
attempt                                      control     verdict
===========================================  ==========  ====================
bare ``「…」`` counts as a quote              —           reintroduces the
                                                         emphasis-mark false
                                                         positive PR #952 fixed
``text_contents LIKE '%quote%'``             —           simplified probe vs
                                                         traditional corpus,
                                                         and elisions
ES ``match_phrase`` decides                  30.0%       punctuation breaks the
                                                         phrase; real canon
                                                         scored as missing
**ES recalls, ``normalise_for_match``        **98.3%**   adopted
adjudicates**
===========================================  ==========  ====================

The control arm feeds quotes the runtime guard already verified as verbatim
back through the resolver. Anything below ~100% there means the instrument is
broken and every other number in the run is noise.

Usage::

    # Precision: hide the model's own citation, see if we recover it.
    python -m eval.recover_citations --control 120

    # Recovery: how much of the unmarked cohort can be given an 出处 at all.
    python -m eval.recover_citations --window-days 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.quote_verifier import (
    _QUOTE_PAIRS,
    MIN_QUOTE_CHARS,
    iter_quote_citations,
    normalise_for_match,
)
from eval.replay_production import CITATION_MARKER, StoredAnswer

EVAL_DIR = Path(__file__).parent
REPORTS_DIR = EVAL_DIR / "reports"

# Same mark families and length window as ``_QUOTE_CITATION_RE``, minus its
# requirement that a citation follow. That requirement is load-bearing at
# runtime — 「」 in Chinese is emphasis, quotation of the user, vernacular gloss
# AND canon citation, and without the bracket marker the guard cannot tell them
# apart (which is why forcing verification on every 「」 would resurrect the
# PR #952 false positive). Here the marker's absence is precisely the population
# under study, so the canon lookup does the disambiguating instead.
QUOTE_ONLY_RE = re.compile(
    "|".join(
        re.escape(o)
        + r"(?P<q" + str(i) + r">[^\n" + re.escape(c) + r"]{" + str(MIN_QUOTE_CHARS) + r",400})"
        + re.escape(c)
        for i, (o, c) in enumerate(_QUOTE_PAIRS.items())
    )
)

# An elided quote ("如是我聞……處") can never be a verbatim substring; test its
# longest intact run instead of scoring the elision as a fabrication.
ELLIPSIS_RE = re.compile(r"…+|\.{3,}|。{2,}")


@dataclass(frozen=True)
class Candidate:
    """One text+fascicle whose body verbatim contains the quote."""

    text_id: int
    cbeta_id: str
    title_zh: str
    juan_num: int


def is_continued_canon(cbeta_id: str) -> bool:
    """卍續藏 (X…) — the canon that is almost entirely commentary.

    Mirrors ``rag_retrieval._is_continued_canon`` (pinned by a test) rather than
    importing it, so this module stays free of the retrieval stack's OpenCC and
    embedding-client imports. Keyed on ``cbeta_id``, never on
    ``buddhist_texts.category`` — that column has 6,318 NULLs.
    """
    return (cbeta_id or "").startswith("X")


def rank_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Root canon first, then a total order so two runs agree.

    Commentary quotes the root text in full, so a root-canon verse matches its
    own 注疏 as readily as itself; naming the 注疏 would be a citation that
    contains the words and misstates the provenance. ES hit order is not stable
    across queries, hence the explicit tiebreak — without it the recovered 出处
    could flip between runs and any measured precision would be measuring the
    sort.
    """
    return sorted(
        candidates,
        key=lambda c: (is_continued_canon(c.cbeta_id), c.text_id, c.juan_num),
    )


def resolution_of(candidates: Sequence[Candidate]) -> dict:
    """Did we find an 出处, and is it the only one?

    ``unique_text`` counts distinct *texts*: the same 经 matching in two 卷 is
    one attribution with a fascicle still to pick, not cross-text ambiguity.
    """
    ranked = rank_candidates(candidates)
    texts = {c.text_id for c in ranked}
    return {
        "resolved": bool(ranked),
        "unique_text": len(texts) == 1,
        "n_texts": len(texts),
        "n_candidates": len(ranked),
        "best": ranked[0] if ranked else None,
    }


def summarise(rows: Sequence[dict]) -> dict:
    """Recovery rates. ``unique_rate`` is denominated in *recovered* quotes.

    Pooling the unrecovered into the unique denominator would blend two
    different failures — "we could not name a text" and "we named several" —
    into one number that means neither.
    """
    if not rows:
        return {}
    recovered = [r for r in rows if r["resolved"]]
    unique = [r for r in recovered if r["unique_text"]]
    return {
        "quotes": len(rows),
        "recovered": len(recovered),
        "recovery_rate": len(recovered) / len(rows),
        "unique_rate": (len(unique) / len(recovered)) if recovered else None,
        "median_texts_when_recovered": (
            sorted(r["n_texts"] for r in recovered)[len(recovered) // 2] if recovered else None
        ),
    }


def quotes_in(answer: str) -> list[str]:
    """Every quoted run long enough for the verifier to have bothered with."""
    out: list[str] = []
    for m in QUOTE_ONLY_RE.finditer(answer or ""):
        for i in range(len(_QUOTE_PAIRS)):
            g = m.group("q" + str(i))
            if g is not None:
                out.append(g)
                break
    return out


def probe_of(quote: str) -> str:
    """The longest intact run of a possibly-elided quote, or '' if too short."""
    best = max(ELLIPSIS_RE.split(quote), key=len).strip("：:，,。 、")
    return best if len(best) >= MIN_QUOTE_CHARS else ""


# ── ES layer (needs the prod index; not exercised in CI) ─────────────────────


async def find_in_canon(es, quote: str, *, index: str, size: int = 25) -> list[Candidate]:
    """Recall with ES, adjudicate with the guard's own normaliser.

    ``match_phrase`` cannot decide this: CJK tokenisation puts boundaries at
    punctuation, so a real quote whose punctuation differs from CBETA's scores
    as absent (control arm: 30%). ES is therefore used only to narrow 19,490
    fascicles to a couple of dozen; the verdict is the same
    ``normalise_for_match`` substring test the runtime guard applies, which folds
    繁简 and strips punctuation (control arm: 98.3%).
    """
    probe = probe_of(quote)
    needle = normalise_for_match(probe)
    if not needle:
        return []

    async def _hits(body: dict) -> list[Candidate]:
        res = await es.search(index=index, body=body)
        found = []
        for h in res["hits"]["hits"]:
            src = h["_source"]
            if needle in normalise_for_match(src.get("content") or ""):
                found.append(
                    Candidate(
                        text_id=src.get("text_id") or 0,
                        cbeta_id=src.get("cbeta_id") or "",
                        title_zh=src.get("title_zh") or "",
                        juan_num=src.get("juan_num") or 0,
                    )
                )
        return found

    fields = ["text_id", "cbeta_id", "title_zh", "juan_num", "content"]
    strict = await _hits({
        "size": size, "_source": fields,
        "query": {"match": {"content": {"query": probe[:30], "operator": "and"}}},
    })
    if strict:
        return strict
    # A long probe can exceed what any single fascicle matches on every term.
    return await _hits({
        "size": size, "_source": fields,
        "query": {"match": {"content": {"query": probe[:30], "minimum_should_match": "70%"}}},
    })


# ── Arms ─────────────────────────────────────────────────────────────────────


async def run_control(es, answers: Sequence[StoredAnswer], *, index: str, n: int, seed: int = 7) -> dict:
    """Precision: hide a verified citation, see whether we recover it.

    Ground truth is the model's own ``【《title》第N卷】`` on quotes the runtime
    guard confirmed verbatim against the retrieved chunk. If the resolver cannot
    reproduce those, it cannot be trusted on the unmarked cohort either.
    """
    truth: list[tuple[str, int | None, str]] = []
    for a in answers:
        if CITATION_MARKER not in (a.answer or ""):
            continue
        hay = [normalise_for_match(s.chunk_text) for s in a.sources]
        for c in iter_quote_citations(a.answer):
            nq = normalise_for_match(c.quote)
            if nq and any(nq in h for h in hay) and probe_of(c.quote):
                truth.append((c.title, c.juan, c.quote))
    sample = random.Random(seed).sample(truth, min(n, len(truth)))

    outcomes: list[dict] = []
    for title, juan, quote in sample:
        cands = await find_in_canon(es, quote, index=index)
        if not cands:
            continue
        outcomes.append(score_outcome(resolution_of(cands), cited_title=title, cited_juan=juan))
    return summarise_control(outcomes, sampled=len(sample), available=len(truth))


def score_outcome(resolution: dict, *, cited_title: str, cited_juan: int | None) -> dict:
    """Grade one recovery against the citation the model itself wrote.

    ``juan_ok`` is deliberately gated on ``title_ok``: a fascicle number cannot
    be correct while its text is wrong, and letting the two float independently
    would let the report claim a 卷号 accuracy the attribution does not support.
    Titles are folded on both sides — the model writes 简体, the corpus 繁體.
    """
    best = resolution.get("best")
    if best is None:
        return {"unique_text": False, "title_ok": False, "juan_ok": False}
    title_ok = normalise_for_match(best.title_zh) == normalise_for_match(cited_title)
    return {
        "unique_text": resolution["unique_text"],
        "title_ok": title_ok,
        "juan_ok": bool(title_ok and cited_juan is not None and best.juan_num == cited_juan),
    }


def summarise_control(outcomes: Sequence[dict], *, sampled: int, available: int) -> dict:
    """Control precision, **split by whether the passage resolved uniquely**.

    The pooled number is close to useless here and actively misleading: measured
    2026-09-02 it read 81%, which is neither of the two populations it averages.
    Passages that live in exactly one text resolve at 96.3%; passages quoted by
    several texts resolve at 40.0%, because the resolver prefers the root canon
    while the model had cited a 注疏 that also contains the words (《地藏本願經科註》
    vs 《地藏菩薩本願經》). Reporting one figure would have hidden the only fact
    that matters for shipping — that a safe subset exists and is identifiable in
    advance by ``unique_text``.
    """
    if not outcomes:
        return {"sampled": sampled, "available": available, "found_rate": 0.0 if sampled else None}

    def bucket(rows: Sequence[dict]) -> dict:
        return {
            "n": len(rows),
            "title_precision": (sum(r["title_ok"] for r in rows) / len(rows)) if rows else None,
            "juan_precision": (sum(r["juan_ok"] for r in rows) / len(rows)) if rows else None,
        }

    unique = [r for r in outcomes if r["unique_text"]]
    ambiguous = [r for r in outcomes if not r["unique_text"]]
    return {
        "sampled": sampled,
        "available": available,
        "found_rate": len(outcomes) / sampled if sampled else None,
        "unique": bucket(unique),
        "ambiguous": bucket(ambiguous),
        "pooled": bucket(outcomes),
    }


async def run_recovery(es, answers: Sequence[StoredAnswer], *, index: str) -> tuple[dict, list[dict]]:
    """Recovery: how much of the unmarked cohort can be given an 出处 at all.

    Only quotes that are *not* already verbatim in that answer's retrieved
    chunks are considered — anything the retriever surfaced was verifiable at
    serve time and is not part of the leak.
    """
    rows: list[dict] = []
    for a in answers:
        if CITATION_MARKER in (a.answer or ""):
            continue
        hay = [normalise_for_match(s.chunk_text) for s in a.sources]
        for q in quotes_in(a.answer):
            nq = normalise_for_match(q)
            if not nq or any(nq in h for h in hay) or not probe_of(q):
                continue
            cands = await find_in_canon(es, q, index=index)
            r = resolution_of(cands)
            rows.append({
                "message_id": a.message_id,
                "quote": q[:80],
                **{k: v for k, v in r.items() if k != "best"},
                "best": asdict(r["best"]) if r["best"] else None,
            })
    return summarise(rows), rows


def generate_report(control: dict, recov: dict, rows: list[dict], *, selection: str) -> str:
    def pct(v):
        return f"{round(v * 100, 1)}%" if isinstance(v, int | float) else "N/A"

    answers = len({r["message_id"] for r in rows if r["resolved"]})
    lines = [
        "# 找回丢失的出处 · 离线回收率评测",
        "",
        f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**选样**: {selection}",
        "",
        "## 对照臂（仪器是否可信）",
        "",
        "把护栏**已判定逐字正确**的引文遮住其引用标记，看解析器能否还原出同一个出处。",
        f"抽样 {control.get('sampled')} / 可用 {control.get('available')}；"
        f"能在藏经里找到 **{pct(control.get('found_rate'))}**"
        "（这一项低于约 100% 即说明召回坏了，其余数字一律作废）。",
        "",
        "| 解析结果 | 条数 | 经名正确 | 卷号也正确 |",
        "|---|---|---|---|",
        f"| **只对应唯一一部经** | {control.get('unique', {}).get('n', 0)} "
        f"| **{pct(control.get('unique', {}).get('title_precision'))}** "
        f"| {pct(control.get('unique', {}).get('juan_precision'))} |",
        f"| 对应多部经 | {control.get('ambiguous', {}).get('n', 0)} "
        f"| {pct(control.get('ambiguous', {}).get('title_precision'))} "
        f"| {pct(control.get('ambiguous', {}).get('juan_precision'))} |",
        f"| *（池化，仅供对照）* | {control.get('pooled', {}).get('n', 0)} "
        f"| *{pct(control.get('pooled', {}).get('title_precision'))}* "
        f"| *{pct(control.get('pooled', {}).get('juan_precision'))}* |",
        "",
        "> **池化的那一行不要读。** 它平均了两个截然不同的总体：唯一解析的高精度，"
        "和多经命中时解析器偏向根本经、而模型标的是注疏所造成的系统性不一致"
        "（《地藏本願經科註》vs《地藏菩薩本願經》——解析器往往更对，但它在推翻"
        "模型自己已核验过的归属）。能不能上线，只取决于第一行。",
        "",
        "## 回收臂（无标记答案里的真经文）",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 候选引文 | {recov.get('quotes', 0)} 条 |",
        f"| **能定出出处** | **{pct(recov.get('recovery_rate'))}**（{recov.get('recovered', 0)} 条，"
        f"涉及 {answers} 篇答案） |",
        f"| 其中只对应唯一一部经 | {pct(recov.get('unique_rate'))} |",
        f"| 命中经数中位 | {recov.get('median_texts_when_recovered')} |",
        "",
        "> 只统计**不在该次召回片段里**的引文——检索已经召回的，serve 时本就可核验，不属于泄漏。",
        "> 「只对应唯一一部经」是关键读数：一句被四十家注疏转引的偈颂，即便定得到根本经，"
        "也要让读者知道它并非该经独有。",
    ]
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Measure whether uncited canon quotes can be given a 出处")
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--limit", type=int, help="Cap answers scanned")
    parser.add_argument("--control", type=int, default=60, help="Control-arm sample size (0 skips)")
    parser.add_argument("--tag", type=str, default="")
    args = parser.parse_args()

    from app.core.elasticsearch import CONTENT_INDEX_NAME, close_es, init_es
    from app.database import async_session
    from eval.replay_production import fetch_stored_answers

    async with async_session() as session:
        answers = await fetch_stored_answers(session, window_days=args.window_days, limit=args.limit)
    if not answers:
        print("没有可分析的答案。")
        return 0

    es = await init_es()
    try:
        control = await run_control(es, answers, index=CONTENT_INDEX_NAME, n=args.control) if args.control else {}
        recov, rows = await run_recovery(es, answers, index=CONTENT_INDEX_NAME)
    finally:
        await close_es()

    selection = f"最近 {args.window_days} 天，{len(answers)} 条答案"
    report = generate_report(control, recov, rows, selection=selection)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag_suffix = f"-{args.tag}" if args.tag else ""
    payload = {"generated_at": timestamp, "selection": selection,
               "control": control, "recovery": recov, "rows": rows}
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        base = REPORTS_DIR / f"recover-{timestamp}{tag_suffix}"
        base.with_suffix(".md").write_text(report, encoding="utf-8")
        base.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = f"\nReport: {base}.md\nRaw: {base}.json"
    except OSError as exc:
        base = Path("/tmp") / f"recover-{timestamp}{tag_suffix}"
        base.with_suffix(".md").write_text(report, encoding="utf-8")
        base.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = (f"\n⚠️  {REPORTS_DIR} 不可写（{exc}）——报告写到了 EPHEMERAL 的 /tmp。"
                 f"\n    修复：chgrp 999 backend/eval/reports && chmod g+w backend/eval/reports"
                 f"\nReport: {base}.md\nRaw: {base}.json")

    print(f"\n{'=' * 60}")
    print(report)
    print(saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
