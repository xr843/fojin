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
  Both fire → is_buddhist=None (ambiguous; conservative — "宁可漏不要错")
  Neither fires → is_buddhist=None

The timeline filter rejects NULL by default, so unknowns drop out.

Run on production:
  python scripts/classify_buddhist_persons.py --dry-run
  python scripts/classify_buddhist_persons.py --dry-run --sample 50
  python scripts/classify_buddhist_persons.py --write

Re-classification:
  Already-tagged rows (is_buddhist=true or =false) are NOT touched on re-run.
  To force re-classification after the regex evolves, first NULL the field:
    UPDATE kg_entities
       SET properties = ((properties::jsonb) - 'is_buddhist')::json
       WHERE entity_type='person' AND properties->>'is_buddhist' IS NOT NULL;
  …then re-run --write.
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

# HARD_BUDDHIST: 本人就是僧的硬证据，几乎只能描述传记主体本人。
# 一旦命中，无视 SOFT 与 SECULAR (除 SECULAR_OVERRIDE)。
HARD_BUDDHIST = re.compile(
    r"出家"                    # 本人动作 (注：偶尔在「其子出家」语境下误伤，罕见)
    r"|受具"                    # 本人受具足戒
    r"|薙染|剃度|剃染|披剃"     # 本人剃度
    r"|譯經|译经"               # 译经师身份 (患/赞助型很少用此词)
    r"|入滅|入灭|示寂|圓寂|圆寂" # 本人死亡词
    # 法号「釋」后跟法名字符 (e.g. 釋雪松/释心道)。
    # 排除「釋氏/釋家/釋門/釋道/釋教/釋徒」等泛指佛教的词 —
    # 「酷信釋氏」(陳思讓) 不应触发 HARD。
    r"|釋(?![氏家門门道教徒])[一-鿿]"
    r"|释(?![氏家门道教徒])[一-鿿]"
    r"|僧[人侶徒衣俗]"           # 僧人/僧侶 等身份词
    r"|為[僧]|出家為僧|遊僧|遊方僧"
    r"|[唐宋元明清晉魏齊梁陳隋][初末]?僧"
    r"|[蜀魏吳][國]?僧"
)

# SOFT_BUDDHIST: 既可指本人身份也可指他人/概念。SOFT only → true，
# SOFT + SECULAR → false。
# 沙門/比丘/寺主 移到这里 (v2 漏洞)：「迎來沙門/立寺主」是患者行为，
# 把汉明帝這類佛教護法误标 HARD → true。
SOFT_BUDDHIST = re.compile(
    r"沙門|沙门"
    r"|比丘尼?"
    r"|寺主"
    r"|和尚|禪師|禅师|法師|法师|律師|律师"
    r"|阿羅漢|阿罗汉|尊者"
    r"|菩薩|菩萨"
    r"|涅槃|涅盘"
    r"|轉法輪|转法轮"
    r"|三藏"
    r"|戒律.*師|戒律.*师"
)

# Override patterns: present in description → must classify as secular even
# if HARD_BUDDHIST also fires.
# - 還俗/歸俗: 短暂出家又返俗，本质世俗 (e.g. 徐孝克 周易学者)
# - 全真/道教 + 出家: 道教徒出家，不算佛教 (e.g. 黃公望 元代道教画家)
# - 廟號/年號: 帝王专属词，僧人不会用。即使「捨身出家」HARD 命中也override
#   (e.g. 蕭衍梁武帝 多次捨身出家但终是皇帝护法不是僧人).
SECULAR_OVERRIDE = re.compile(
    r"還俗|还俗|歸俗|归俗"
    r"|(?:全真|道教)[^。]{0,8}出家"
    r"|廟號|庙号|年號|年号"
)

# STRONG_SECULAR: 命中即偏向世俗。HARD 仍优先 (不会被这覆盖)，但 SOFT 配
# SECULAR 即归 false。新增世俗职业（诗人/画家/书法家/学者/博士/建筑师/工程师等）
# 是 v3 audit 发现的 false-positive 来源 (傅維早/陶潛/学者类)。
STRONG_SECULAR = re.compile(
    r"孔[子門门]|儒[家學学]|孟[子軻轲]"
    r"|道家|道教|道士|全真教|龍門派|龙门派"
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
    # 帝王登基/统治/谥号词 — 配合迎来沙门/立寺等护法行为，区分真僧 vs 护法
    r"|登基|即位|在位\s*\d|年號|年号"
    r"|諡[^，。]{0,3}|谥[^，。]{0,3}|廟號|庙号|顯宗|玄宗"
    r"|皇后|皇太|貴妃|贵妃|嬪|嫔|大臣"
    r"|帝師.*[儒道]|国师.*儒"
    r"|魯國|齊國|楚國"
    r"|韓非|商鞅|李斯|蘇秦|張儀|管仲|樂毅|白起|韓信|蕭何|張良|諸葛"
    # ── 新增：世俗职业（v3 audit 抓到的 false positive 模式）
    r"|詩人|诗人|散文家|小說家|小说家|文人|作家|翻譯家|翻译家"
    r"|畫家|画家|書法家|书法家|藝術家|艺术家|金石家"
    r"|建築師|建筑师|工程師|工程师|攝影師|摄影师"
    r"|科學家|科学家|医生|醫生|商人|實業家|实业家|外交官"
    r"|文學博士|哲學博士|歷史學家|历史学家"
    r"|官員|官员|議員|议员|大臣"
    r"|教授|校長|校长"       # 注意：佛学院教授会被 HARD/SOFT 抵消，不影响真僧
)

# Strip parenthesised DILA / CBETA citation tails before applying regex —
# without this, "陳朝將軍。（唐僧索引：329）" matches STRONG_BUDDHIST on the
# stray 「僧」 in the citation marker and gets mis-tagged as Buddhist.
_CITATION_PAREN = re.compile(r"[（(][^）)]*(?:索引|疑年錄|疑年录|百品|宋史|新唐書|新唐书|wikipedia|http|wikisource|淵四|渊四|T\d|X\d|g\d|B\d)[^）)]*[）)]")


def classify(description: str | None) -> str | None:
    """Return 'true', 'false', or None (ambiguous).

    Three-layer logic:
      1. SECULAR_OVERRIDE (還俗 / 全真道教出家) → "false" — even if HARD
         buddhist fires. Catches 徐孝克 (周易学者临时出家又还俗),
         黃公望 (元代全真教画家).
      2. HARD_BUDDHIST (本人是僧的硬证据：出家/受具/剃染/沙門/比丘/X朝僧/
         譯經/釋X 法号) → "true". Even if secular profession 兼任 (e.g.
         少年教授后出家).
      3. SOFT_BUDDHIST (法号/称谓，可能是他人) combined with SECULAR →
         "false" (e.g. 傅維早 建築師受法师托修寺 / 陶潛 詩人访慧远).
         SOFT only without SECULAR → "true" (法号体的真僧).
      4. SECULAR only → "false".
      5. Neither → None (ambiguous, dropped by timeline filter).
    """
    if not description:
        return None
    cleaned = _CITATION_PAREN.sub("", description)

    # Layer 1: secular override beats everything.
    if SECULAR_OVERRIDE.search(cleaned):
        return "false"

    hard = bool(HARD_BUDDHIST.search(cleaned))
    soft = bool(SOFT_BUDDHIST.search(cleaned))
    secular = bool(STRONG_SECULAR.search(cleaned))

    # Layer 2: hard buddhist wins over secular profession.
    if hard:
        return "true"

    # Layer 3: soft alone vs soft+secular.
    if soft and secular:
        return "false"
    if soft:
        return "true"

    # Layer 4: secular alone.
    if secular:
        return "false"

    # Layer 5: neither.
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
