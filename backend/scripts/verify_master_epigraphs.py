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

# Names a master's own works are filed under in buddhist_texts.translator. Needed
# because the DB spells some of them differently from name_zh — 蕅益's works are
# attributed to his dharma name 智旭, and Tibetan/Pali names have 繁/简 variants.
#
# This drives the NEGATIVE half of the check, and it exists because the positive
# half alone was not enough: the first cut of the gallery verified the 5 masters
# that HAD a line and never checked the 10 that didn't — so 玄奘's card claimed
# 「本站未收其本人著作」 while 《成唯識論》(T1585) sat right there in the corpus, and
# 蕅益's did the same over 《教觀綱宗》(T1939). A card that states something we can't
# back is the exact failure this product exists to prevent, so assert it can't.
CORPUS_ALIASES: dict[str, list[str]] = {
    "nagarjuna": ["龍樹", "龙树"],
    "zhiyi": ["智顗"],
    "huineng": ["慧能", "宗寶"],
    "xuanzang": ["玄奘"],
    "fazang": ["法藏"],
    "kumarajiva": ["鳩摩羅什", "鸠摩罗什"],
    "yinguang": ["印光"],
    "ouyi": ["智旭", "蕅益"],
    "xuyun": ["虛雲", "虚云"],
    "milarepa": ["米拉日巴", "密勒日巴"],
    "ajahn-chah": ["阿姜查"],
    "tsongkhapa": ["宗喀巴"],
    "atisha": ["阿底峽", "阿底峡"],
    "buddhaghosa": ["覺音", "觉音"],
    "mahasi-sayadaw": ["馬哈希", "马哈希"],
}


async def _works_we_host(s: AsyncSession, master_id: str) -> list[tuple]:
    """Texts in our corpus attributed to this master (author or translator)."""
    aliases = CORPUS_ALIASES.get(master_id, [])
    if not aliases:
        return []
    rows = await s.execute(
        sql(
            "SELECT cbeta_id, title_zh FROM buddhist_texts "
            "WHERE translator ILIKE ANY(:pats) ORDER BY id LIMIT 5"
        ),
        {"pats": [f"%{a}%" for a in aliases]},
    )
    return list(rows.fetchall())


async def main() -> int:
    engine = create_async_engine(settings.database_url)
    failures: list[str] = []
    checked = 0

    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        for mid, m in MASTERS.items():
            ep = m.epigraph
            if ep is None:
                # The card shows 未设. Prove we are entitled to say that: if the
                # corpus DOES hold this master's own work, a line should have been
                # curated from it and the card is quietly misleading.
                works = await _works_we_host(s, mid)
                if works:
                    listed = "; ".join(f"{c}《{t}》" for c, t in works[:3])
                    failures.append(
                        f"{mid}: card shows 未设, but we host his work — {listed}. Curate a line."
                    )
                    print(f"  ⚠️  {m.name_zh:<12} 未设,但库中有其著作:{listed}")
                else:
                    print(f"  —  {m.name_zh:<12} 未设 (corpus holds none of his work — confirmed)")
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
