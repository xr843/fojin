"""Re-verify every 祖师长廊 epigraph against the corpus. Exits non-zero on any miss.

    docker compose exec -T backend python -u scripts/verify_master_epigraphs.py

Why this exists
---------------
The gallery's whole claim is that a master's card only carries a line we can back
up. That was established by hand once (2026-07-12); this script makes it a check
anyone can re-run — after a data reimport, a text_id change, or a new epigraph.

It reuses ``quote_verifier._normalise`` on purpose. Verifying by naive substring
match is a TRAP that already bit us twice:

  1. CBETA content hard-wraps mid-word — 摩訶止觀 stores ``法\\n\\n性寂然名「止」`` —
     so ``"法性寂然名止" in content`` is False even though the line is right there.
  2. The corpus is 繁體 while our UI/quotes drift 简体, and CBETA punctuation differs
     from anything a human types.

``_normalise`` handles all of it (NFKC + 繁→简 fold + strip punctuation/whitespace),
which is precisely why the production quote-verifier uses it. Any bespoke matcher
here would re-introduce the false-negatives it exists to prevent.

The other half of the trap is the search API: ``/api/search/content`` is token-fuzzy,
so its top hit is NOT proof — it cheerfully "finds" 印光's 「敦倫盡分」 inside 《長阿含經》.
This script never searches; it reads the exact cited juan and checks it contains the
line. That is the only claim the card makes.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.services.master_profiles import MASTERS
from app.services.quote_verifier import _normalise


async def main() -> int:
    engine = create_async_engine(settings.database_url)
    failures: list[str] = []
    checked = 0

    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        for mid, m in MASTERS.items():
            ep = m.epigraph
            if ep is None:
                print(f"  —  {m.name_zh:<12} 未设 (no work of his in the corpus)")
                continue

            checked += 1
            # lang='lzh' matters: text_contents is unique on (text_id, juan_num, lang),
            # so a juan can also hold an English/Pali rendering. Comparing a 漢文 quote
            # against a translation would fail for the wrong reason.
            row = (
                await s.execute(
                    sql(
                        "SELECT content FROM text_contents "
                        "WHERE text_id = :tid AND juan_num = :juan AND lang = 'lzh' LIMIT 1"
                    ),
                    {"tid": ep.text_id, "juan": ep.juan},
                )
            ).first()

            if row is None or not row[0]:
                failures.append(f"{mid}: no content for text_id={ep.text_id} juan={ep.juan}")
                print(f"  ✗  {m.name_zh:<12} 卷内容取不到 (text_id={ep.text_id} juan={ep.juan})")
                continue

            if _normalise(ep.quote) in _normalise(row[0]):
                print(
                    f"  ✅ {m.name_zh:<12} 「{ep.quote}」 "
                    f"— {ep.cbeta_id}《{ep.title_zh}》卷{ep.juan}"
                )
            else:
                failures.append(
                    f"{mid}: 「{ep.quote}」 NOT found in {ep.cbeta_id} 卷{ep.juan}"
                )
                print(f"  ❌ {m.name_zh:<12} 「{ep.quote}」 不在 {ep.cbeta_id} 卷{ep.juan}")

            # The card links the quote into the reader under this master's own
            # scope; if the cited text isn't in his scope, the card and the RAG
            # disagree (exactly the 慧能 bug).
            if m.fojin_text_ids and ep.text_id not in m.fojin_text_ids:
                failures.append(
                    f"{mid}: epigraph text_id={ep.text_id} outside RAG scope {m.fojin_text_ids}"
                )

    await engine.dispose()

    print(f"\n{checked} epigraph(s) checked, {len(failures)} problem(s).")
    for f in failures:
        print(f"  !! {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
