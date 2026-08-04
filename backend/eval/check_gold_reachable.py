"""Gate: every gold source in the test set must actually be retrievable.

A gold entry naming a text that isn't in the corpus — or is in the corpus but
has no embeddings — makes its metric structurally unachievable. The eval then
reports a permanent miss that no retrieval change can ever fix, and the ruler
quietly stops measuring the thing it claims to measure. That already happened:
《慈经》 (prac-006) and 《入菩萨行论》 (prac-012) were gold for months while being
absent from the corpus entirely.

Run where the corpus DB is reachable (prod container, cwd /app):

    python -m eval.check_gold_reachable            # report + exit 1 on unreachable 正解
    python -m eval.check_gold_reachable --strict   # also fail on unreachable 等价来源

Exit codes: 0 = all reachable, 1 = at least one unreachable gold.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text as sql_text

from app.database import async_session
from eval.retrieval_metrics import (
    LENIENT_RELEVANCE,
    STRICT_RELEVANCE,
    gold_entries,
    normalize_title,
)

TEST_SET_PATH = Path(__file__).parent / "test_set.json"


async def _corpus_index() -> dict[str, int]:
    """normalized title -> max embedded chunk count across texts with that title."""
    async with async_session() as session:
        rows = (
            await session.execute(
                sql_text(
                    "SELECT bt.title_zh, count(te.id) AS chunks "
                    "FROM buddhist_texts bt "
                    "LEFT JOIN text_embeddings te ON te.text_id = bt.id "
                    "WHERE bt.lang = 'lzh' "
                    "GROUP BY bt.id, bt.title_zh"
                )
            )
        ).fetchall()
    index: dict[str, int] = defaultdict(int)
    for title, chunks in rows:
        key = normalize_title(title)
        if key:
            index[key] = max(index[key], int(chunks or 0))
    return dict(index)


def _lookup(index: dict[str, int], title_key: str) -> int | None:
    """Embedded chunk count for a gold title, or None if no such text exists.

    Falls back to a containment match so a gold title that is a distinctive
    prefix/substring of the canonical one (《楞严经》 vs the full 20-char title)
    still resolves — the same tolerance ``source_matches_gold`` callers expect.
    """
    if title_key in index:
        return index[title_key]
    hits = [n for key, n in index.items() if title_key and title_key in key]
    return max(hits) if hits else None


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="also fail when a relevance=1 等价来源 is unreachable")
    args = parser.parse_args()

    questions = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))["questions"]
    index = await _corpus_index()

    missing: list[tuple[str, str, int, str]] = []   # (qid, title, relevance, reason)
    checked = 0
    for q in questions:
        for gold in gold_entries(q, min_relevance=LENIENT_RELEVANCE):
            checked += 1
            chunks = _lookup(index, gold["title"])
            if chunks is None:
                missing.append((q["id"], gold["title"], gold["relevance"], "语料中无此文本"))
            elif chunks == 0:
                missing.append((q["id"], gold["title"], gold["relevance"], "有文本但无 embedding"))

    print(f"检查 {checked} 条 gold（{len(questions)} 题），语料中 lzh 文本 {len(index)} 种")
    if not missing:
        print("✅ 全部可达")
        return 0

    fatal = [m for m in missing if m[2] >= STRICT_RELEVANCE]
    print(f"\n❌ 不可达 {len(missing)} 条（其中正解 relevance>=2: {len(fatal)}）\n")
    for qid, title, relevance, reason in missing:
        mark = "正解" if relevance >= STRICT_RELEVANCE else "等价"
        print(f"  [{qid}] {mark} r={relevance}  {title}  —— {reason}")

    print("\n处理方式：把该典籍导入语料，或把该 gold 换成语料内等效的权威出处。")
    return 1 if (fatal or args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
