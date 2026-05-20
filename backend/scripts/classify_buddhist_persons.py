"""
Classify person entities into is_buddhist={true,false} for the /kg/timeline filter.

Why this exists:
- kg_entities has 43k person rows; most carry no is_buddhist flag.
- /kg/timeline previously displayed every dated person, surfacing Confucian
  disciples (孔門十哲), 周文王/召公, 老子, 范蠡, etc.  Users expect only
  Buddhist historical figures.
- We do not have a clean "is_buddhist" source field, but DILA descriptions
  are reliably tagged: monks carry titles (法師/禪師/律師), are described as
  出家/受具/譯經, etc.; secular figures carry 諸侯/丞相/儒/孔門 etc.

This script tags is_buddhist for all person rows currently NULL, using
conservative regex:

  STRONG_BUDDHIST regex → is_buddhist=true
  STRONG_SECULAR regex (and no buddhist marker) → is_buddhist=false
  ambiguous → leave NULL  (the timeline filter will reject NULL by default,
                          so unknowns drop out)

Run on production:
  python scripts/classify_buddhist_persons.py --dry-run
  python scripts/classify_buddhist_persons.py --dry-run --sample 50
  python scripts/classify_buddhist_persons.py --write
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

# Patterns that, if present, mark the person as Buddhist.
# Tuned against DILA narratives. False-positive risk audited by sampling.
STRONG_BUDDHIST = re.compile(
    r"出家"
    r"|受具"
    r"|薙染|剃度|剃染"
    r"|譯經|译经"
    r"|沙門|沙门"
    r"|比丘尼?"
    r"|和尚"
    r"|禪師|禅师"
    r"|法師|法师"
    r"|律師|律师"
    r"|住持|方丈|寺主"
    r"|入滅|入灭|示寂|圓寂|圆寂"
    r"|阿羅漢|阿罗汉|尊者"
    r"|釋[迦氏]|释[迦氏]"      # 釋迦/釋氏/釋…(法号「释」开头)
    r"|菩薩|菩萨"
    r"|涅槃|涅盘"
    r"|轉法輪|转法轮"
    r"|三藏"
    r"|戒律.*師|戒律.*师"
    r"|僧"                     # broad — last because also in 僧侶/僧人
)

# Patterns that, if present AND no Buddhist marker, mark the person secular.
# Intentionally broad: catches 孔門十哲, 周/漢/明 dynasty officials, scholars,
# warriors, royalty.
STRONG_SECULAR = re.compile(
    r"孔[子門门]|儒[家學学]|孟[子軻轲]"
    r"|道家|道教.*真人"        # 真人 alone could be Buddhist (修真), require 道教
    r"|諸侯|诸侯"
    r"|皇帝|帝[號号]|登基|即位"
    r"|丞相|宰相|相國|相国"
    r"|尚書|尚书"
    r"|科舉|科举|狀元|状元|進士|进士|舉人|举人|秀才"
    r"|大將軍|大将军|武將|武将|將軍|将军"
    r"|大夫"
    r"|郡守|太守|刺史|縣令|县令|知府|知州|知縣|知县"
    r"|周公|召公|周文王|周武王|周成王|周康王"
    r"|魯[君公侯]|齊[君公侯]|晉[君公侯]|宋[君公侯]|衛[君公侯]|楚[君公侯]"
    r"|文王|武王|成王|康王|宣王|幽王|平王|桓王|莊王|釐王|惠王|襄王|頃王|匡王|定王|簡王|靈王|景王|敬王|元王|貞定王|考王|威烈王|安王|烈王|顯王|慎靚王|赧王"
    r"|秦始皇|漢高祖|漢武帝|唐太宗|宋太祖|明太祖|清聖祖|清世宗|清高宗"
    r"|帝師.*[儒道]|国师.*儒"
    r"|魯國|齊國|楚國"
    r"|韓非|商鞅|李斯|蘇秦|張儀|管仲|樂毅|白起|韓信|蕭何|張良|諸葛"
)

# A whitelist of strings that, even if matched by STRONG_SECULAR, suggests the
# person is still a Buddhist (e.g. 帝師 of a Tibetan tradition). When matched,
# we *re-prefer* the buddhist classification.  Used sparingly.
SECULAR_OVERRIDE_TO_BUDDHIST = re.compile(
    r"國師.*佛|国师.*佛"
    r"|帝師.*喇嘛|帝师.*喇嘛"
    r"|帝師.*薩迦|帝师.*萨迦"
    r"|出家|受具|譯經|譯經"
)


# Strip parenthesised DILA / CBETA citation tails before applying regex —
# without this, "陳朝將軍。（唐僧索引：329）" matches STRONG_BUDDHIST on the
# stray 「僧」 in the citation marker and gets mis-tagged as Buddhist.
_CITATION_PAREN = re.compile(r"[（(][^）)]*(?:索引|疑年錄|疑年录|百品|宋史|新唐書|新唐书|wikipedia|http|wikisource|淵四|渊四|T\d|X\d|g\d|B\d)[^）)]*[）)]")


def classify(description: str | None) -> str | None:
    """Return 'true', 'false', or None (ambiguous)."""
    if not description:
        return None
    cleaned = _CITATION_PAREN.sub("", description)
    buddhist_hit = bool(STRONG_BUDDHIST.search(cleaned))
    secular_hit = bool(STRONG_SECULAR.search(cleaned))

    if buddhist_hit and not secular_hit:
        return "true"
    if buddhist_hit and secular_hit:
        # Both fired — try the override regex; otherwise prefer buddhist
        # (secular markers like 大將 can appear in monk biographies as
        # 出家前 background).
        if SECULAR_OVERRIDE_TO_BUDDHIST.search(description):
            return "true"
        return "true"
    if secular_hit and not buddhist_hit:
        return "false"
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(*, write: bool, sample_size: int) -> None:
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        # Pull all persons whose is_buddhist is NOT set.
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, name_zh, description
                    FROM kg_entities
                    WHERE entity_type='person'
                      AND (properties->>'is_buddhist' IS NULL)
                    """
                )
            )
        ).all()
        print(f"Persons with NULL is_buddhist: {len(rows):,}", file=sys.stderr)

        verdict: list[tuple[int, str, str]] = []  # (id, name, classification)
        stats = Counter()
        for r in rows:
            v = classify(r.description)
            if v is None:
                stats["ambiguous"] += 1
            else:
                stats[v] += 1
                verdict.append((r.id, r.name_zh, v))

        print("\n=== Classification stats ===", file=sys.stderr)
        for k in ("true", "false", "ambiguous"):
            print(f"  {k:<10} {stats[k]:>6,}", file=sys.stderr)

        # Sample for human review
        if sample_size > 0:
            print(f"\n=== Sample {sample_size} from each bucket ===", file=sys.stderr)
            for cls in ("true", "false"):
                pool = [v for v in verdict if v[2] == cls]
                sample = random.sample(pool, min(sample_size, len(pool)))
                print(f"\n--- {cls} ({len(pool):,}) ---", file=sys.stderr)
                for vid, vname, _ in sample:
                    desc_row = next(r for r in rows if r.id == vid)
                    snippet = (desc_row.description or "")[:90].replace("\n", " ")
                    print(f"  {vid:>6}  {vname:<10}  {snippet}", file=sys.stderr)

        if not write:
            print("\n(dry-run; no DB writes)", file=sys.stderr)
            return

        # Write classifications. We DO NOT touch the 188 rows already marked
        # false — those were curated.  Only set what was NULL.
        print(f"\nWriting {len(verdict):,} classifications...", file=sys.stderr)
        true_count = sum(1 for v in verdict if v[2] == "true")
        false_count = sum(1 for v in verdict if v[2] == "false")
        # Batched updates for speed.
        for cls in ("true", "false"):
            ids = [v[0] for v in verdict if v[2] == cls]
            if not ids:
                continue
            # Chunk to keep parameter list reasonable.
            for i in range(0, len(ids), 500):
                chunk = ids[i : i + 500]
                await session.execute(
                    text(
                        """
                        UPDATE kg_entities
                        SET properties = (
                          (properties::jsonb) || jsonb_build_object('is_buddhist', cast(:cls AS text))
                        )::json
                        WHERE id = ANY(:ids)
                          AND entity_type = 'person'
                          AND (properties->>'is_buddhist' IS NULL)
                        """
                    ),
                    {"cls": cls, "ids": chunk},
                )
        await session.commit()
        print(f"Done. tagged true={true_count:,} false={false_count:,}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="actually write to DB")
    ap.add_argument("--sample", type=int, default=20, help="N samples per bucket to print")
    args = ap.parse_args()
    asyncio.run(run(write=args.write, sample_size=args.sample))


if __name__ == "__main__":
    main()
