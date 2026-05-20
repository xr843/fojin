"""
Backfill person coordinates v3 — country-aware, dynasty-scored desc_match.

Why this replaces v2:
- v2 used naive substring match on temple names; same-name temples across CN/JP/KR
  collided (e.g. 唐代僧人投到韩国清凉寺). PR #466 had to whitelist out
  `desc_match:*` from the geo map.
- v3 uses person.dynasty (49% coverage) to pin country, then scores temple
  candidates within the matching country. Unambiguous temple names are accepted
  unconditionally; ambiguous names require a dynasty signal.

Writes geo_source = 'desc_match_v3:<country>:<temple>:<score>'.

Usage:
  python scripts/backfill_person_coords_v3.py --dry-run            # produce stats + sample CSV
  python scripts/backfill_person_coords_v3.py --dry-run --sample 100 > sample.csv
  python scripts/backfill_person_coords_v3.py --write              # write to DB (after review)
  python scripts/backfill_person_coords_v3.py --min-score 0.6      # raise threshold
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


# ---------------------------------------------------------------------------
# Dynasty → country/era mapping
# ---------------------------------------------------------------------------
# Country uses the same values stored in monastery.properties->>'country':
#   'CN', '日本', '韩国', '朝鲜', '越南', '台湾', '印度', ...
# Multiple acceptable countries means the temple country may match any of them.
#
# Era (year_start, year_end) is approximate — used only to reject temples
# clearly founded later than the person's lifetime, not for fine-grained
# matching.

DYNASTY_MAP: dict[str, tuple[tuple[str, ...], tuple[int, int]]] = {
    # 中国 ----------------------------------------------------------------
    "東漢": (("CN",), (25, 220)),
    "東漢末": (("CN",), (25, 220)),
    "漢朝": (("CN",), (-202, 220)),
    "西漢": (("CN",), (-202, 9)),
    "三國": (("CN",), (220, 280)),
    "曹魏": (("CN",), (220, 266)),
    "吳": (("CN",), (222, 280)),
    "西晉": (("CN",), (265, 316)),
    "東晉": (("CN",), (317, 420)),
    "晉": (("CN",), (265, 420)),
    "晉朝": (("CN",), (265, 420)),
    "十六國": (("CN",), (304, 439)),
    "前秦": (("CN",), (351, 394)),
    "後秦": (("CN",), (384, 417)),
    "姚秦": (("CN",), (384, 417)),
    "符秦": (("CN",), (351, 394)),
    "前涼": (("CN",), (320, 376)),
    "北涼": (("CN",), (397, 439)),
    "南北朝": (("CN",), (420, 589)),
    "劉宋": (("CN",), (420, 479)),
    "南齊": (("CN",), (479, 502)),
    "南梁": (("CN",), (502, 557)),
    "梁": (("CN",), (502, 557)),
    "南陳": (("CN",), (557, 589)),
    "陳": (("CN",), (557, 589)),
    "北魏": (("CN",), (386, 534)),
    "元魏": (("CN",), (386, 534)),
    "北齊": (("CN",), (550, 577)),
    "北周": (("CN",), (557, 581)),
    "北朝": (("CN",), (386, 581)),
    "南朝": (("CN",), (420, 589)),
    "南詔": (("CN",), (738, 902)),
    "隋": (("CN",), (581, 618)),
    "隋朝": (("CN",), (581, 618)),
    "唐": (("CN",), (618, 907)),
    "唐朝": (("CN",), (618, 907)),
    "武周": (("CN",), (690, 705)),
    "五代十國": (("CN",), (907, 979)),
    "後梁": (("CN",), (907, 923)),
    "後唐": (("CN",), (923, 937)),
    "後晉": (("CN",), (936, 947)),
    "後漢": (("CN",), (947, 951)),
    "後周": (("CN",), (951, 960)),
    "宋": (("CN",), (960, 1279)),
    "宋朝": (("CN",), (960, 1279)),
    "北宋": (("CN",), (960, 1127)),
    "南宋": (("CN",), (1127, 1279)),
    "遼": (("CN",), (916, 1125)),
    "金": (("CN",), (1115, 1234)),
    "西夏": (("CN",), (1038, 1227)),
    "蒙古": (("CN",), (1206, 1271)),
    "元": (("CN",), (1271, 1368)),
    "元朝": (("CN",), (1271, 1368)),
    "明": (("CN",), (1368, 1644)),
    "明朝": (("CN",), (1368, 1644)),
    "清": (("CN",), (1644, 1912)),
    "清朝": (("CN",), (1644, 1912)),
    "民國": (("CN", "台湾"), (1912, 1949)),
    "民国": (("CN", "台湾"), (1912, 1949)),
    # 日本 ----------------------------------------------------------------
    "日本": (("日本",), (538, 2000)),
    # 朝鲜半岛 -- 半岛同名寺院在朝鲜或韩国都能命中
    "朝鮮": (("韩国", "朝鲜"), (1392, 1897)),
    "朝鲜": (("韩国", "朝鲜"), (1392, 1897)),
    "高麗": (("韩国", "朝鲜"), (918, 1392)),
    "高丽": (("韩国", "朝鲜"), (918, 1392)),
    "新羅": (("韩国",), (-57, 935)),
    "新罗": (("韩国",), (-57, 935)),
    "百濟": (("韩国",), (-18, 660)),
    "百济": (("韩国",), (-18, 660)),
    # 印度 — 不投坐标（见下方 SKIP_COUNTRIES）
    "印度": (("印度",), (-500, 1200)),
}

# Person countries we refuse to backfill (古印度论师位置历史地理过于模糊)
SKIP_COUNTRIES: set[str] = {"印度"}

# Default country when person has no dynasty: fall back to CN (the prior assumption)
DEFAULT_COUNTRIES: tuple[str, ...] = ("CN",)


def parse_dynasty(raw: str | None) -> tuple[set[str], tuple[int, int] | None]:
    """Resolve a (possibly composite) dynasty value to allowed countries + era.

    DILA sometimes stores composite values like "南宋;元" or "金;蒙古"; whitespace
    and newlines also leak in. Split on common separators, look each token up,
    union the countries, widen the era span.
    """
    if not raw:
        return set(DEFAULT_COUNTRIES), None
    tokens = re.split(r"[;；,，/／\s]+", raw.strip())
    countries: set[str] = set()
    starts: list[int] = []
    ends: list[int] = []
    for tok in tokens:
        if not tok:
            continue
        info = DYNASTY_MAP.get(tok)
        if not info:
            continue
        countries.update(info[0])
        starts.append(info[1][0])
        ends.append(info[1][1])
    if not countries:
        return set(DEFAULT_COUNTRIES), None
    return countries, (min(starts), max(ends))


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass
class TempleCandidate:
    name: str
    lat: float
    lng: float
    country: str | None
    founded_year: int | None  # currently None — reserved for future


@dataclass
class ScoredMatch:
    person_id: int
    person_name: str
    person_dynasty: str | None
    temple_name: str
    temple_country: str | None
    temple_lat: float
    temple_lng: float
    score: float
    same_name_count: int  # how many temples share this name
    reason: str


def score_match(
    *,
    person_dynasty_raw: str | None,
    description: str,
    candidates: list[TempleCandidate],
    same_name_count: int,
) -> ScoredMatch | None:
    """Pick the best temple candidate, or None if cross-country ambiguity unresolved.

    Score components (base 1.0):
      +0.4 if exactly one candidate survives the country filter
      +0.2 if temple name length >= 5 (longer = less collision risk)
      -0.1 if temple name length == 3 (more collision)
      -0.2 if same_name_count > 5
      -0.2 if same_name_count > 10

    Refusal cases (return None):
      a. Person's dynasty implies a country (e.g. 日本/印度) the temple is not in.
      b. No dynasty + multiple surviving candidates spanning >1 country.
      c. Allowed countries are entirely in SKIP_COUNTRIES (e.g. 印度).
    """
    allowed_countries, _era = parse_dynasty(person_dynasty_raw)
    if allowed_countries.issubset(SKIP_COUNTRIES):
        return None

    # Filter candidates by country; treat missing country as 'CN'
    filtered = [c for c in candidates if (c.country or "CN") in allowed_countries]
    if not filtered:
        return None

    surviving_countries = {(c.country or "CN") for c in filtered}
    # Cross-country ambiguity with no dynasty disambiguator → refuse
    if len(surviving_countries) > 1 and not person_dynasty_raw:
        return None

    # Pick: prefer candidate matching the first allowed country (priority order)
    chosen = filtered[0]
    if person_dynasty_raw:
        for ac in allowed_countries:
            match = next((c for c in filtered if (c.country or "CN") == ac), None)
            if match:
                chosen = match
                break

    score = 1.0
    name_len = len(chosen.name)
    if name_len >= 5:
        score += 0.2
    elif name_len == 3:
        score -= 0.1
    if len(filtered) == 1:
        score += 0.4
    if same_name_count > 5:
        score -= 0.2
    if same_name_count > 10:
        score -= 0.2

    reason = (
        f"countries={sorted(allowed_countries)}; "
        f"survivors={len(filtered)}/{len(candidates)} "
        f"({','.join(sorted(surviving_countries))}); "
        f"same_name={same_name_count}; name_len={name_len}"
    )
    return ScoredMatch(
        person_id=-1,
        person_name="",
        person_dynasty=person_dynasty_raw,
        temple_name=chosen.name,
        temple_country=chosen.country,
        temple_lat=chosen.lat,
        temple_lng=chosen.lng,
        score=score,
        same_name_count=same_name_count,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def load_temples(session: AsyncSession) -> tuple[
    dict[str, list[TempleCandidate]], dict[str, int]
]:
    """Return {temple_name: [candidates...]}, {temple_name: same_name_count}."""
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    name_zh,
                    (properties->>'latitude')::float AS lat,
                    (properties->>'longitude')::float AS lng,
                    properties->>'country' AS country
                FROM kg_entities
                WHERE entity_type = 'monastery'
                  AND properties->>'latitude' IS NOT NULL
                  AND properties->>'longitude' IS NOT NULL
                  AND length(name_zh) >= 3
                """
            )
        )
    ).all()

    by_name: dict[str, list[TempleCandidate]] = {}
    for r in rows:
        by_name.setdefault(r.name_zh, []).append(
            TempleCandidate(
                name=r.name_zh,
                lat=r.lat,
                lng=r.lng,
                country=r.country,
                founded_year=None,
            )
        )
    counts = {k: len(v) for k, v in by_name.items()}
    return by_name, counts


async def load_persons(session: AsyncSession) -> list[dict]:
    """Load candidates for v3 re-evaluation.

    Two pools:
      1. No-coord persons (greenfield)
      2. Existing desc_match:* persons (v2-tagged — currently filtered out of
         the map by knowledge_graph whitelist; we re-score them under v3 logic).

    teacher_hop:* is intentionally excluded from this PR (see project memo).
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    id,
                    name_zh,
                    description,
                    properties->>'dynasty' AS dynasty,
                    properties->>'geo_source' AS geo_source,
                    properties->>'latitude' AS old_lat,
                    properties->>'longitude' AS old_lng
                FROM kg_entities
                WHERE entity_type = 'person'
                  AND description IS NOT NULL
                  AND length(description) >= 10
                  AND (
                    (properties->>'latitude') IS NULL
                    OR properties->>'geo_source' LIKE 'desc_match:%'
                  )
                ORDER BY id
                """
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def find_temple_in_description(desc: str, temple_names: list[str]) -> str | None:
    """Return the longest temple name that appears in the description."""
    best = None
    best_len = 0
    for name in temple_names:
        if len(name) > best_len and name in desc:
            best = name
            best_len = len(name)
    return best


async def run(
    *,
    write: bool,
    min_score: float,
    sample_size: int,
    sample_csv: str | None,
) -> None:
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        print("Loading temples...", file=sys.stderr)
        temples_by_name, same_name_counts = await load_temples(session)
        all_temple_names = sorted(temples_by_name.keys(), key=len, reverse=True)
        print(f"  {len(all_temple_names):,} unique temple names, "
              f"{sum(len(v) for v in temples_by_name.values()):,} temples", file=sys.stderr)

        print("Loading persons without coords...", file=sys.stderr)
        persons = await load_persons(session)
        print(f"  {len(persons):,} persons to process", file=sys.stderr)

        # Score each person
        matches: list[ScoredMatch] = []
        no_temple_hit = 0
        no_match_score = 0
        had_v2 = sum(1 for p in persons if (p.get("geo_source") or "").startswith("desc_match:"))
        was_null = len(persons) - had_v2
        print(f"  ({had_v2:,} re-eval v2, {was_null:,} greenfield)", file=sys.stderr)

        for p in persons:
            temple_name = find_temple_in_description(p["description"], all_temple_names)
            if not temple_name:
                no_temple_hit += 1
                continue
            candidates = temples_by_name[temple_name]
            m = score_match(
                person_dynasty_raw=p["dynasty"],
                description=p["description"],
                candidates=candidates,
                same_name_count=same_name_counts[temple_name],
            )
            if m is None:
                no_match_score += 1
                continue
            m.person_id = p["id"]
            m.person_name = p["name_zh"]
            if m.score >= min_score:
                matches.append(m)

        # Stats
        print("\n=== STATS ===", file=sys.stderr)
        print(f"Persons scanned:           {len(persons):,}", file=sys.stderr)
        print(f"No temple in description:  {no_temple_hit:,}", file=sys.stderr)
        print(f"Filtered (no valid match): {no_match_score:,}", file=sys.stderr)
        print(f"Accepted matches:          {len(matches):,}  (>= {min_score})", file=sys.stderr)

        bucket = Counter()
        for m in matches:
            if m.score >= 1.4:
                bucket["1.4+"] += 1
            elif m.score >= 1.2:
                bucket["1.2-1.4"] += 1
            elif m.score >= 1.0:
                bucket["1.0-1.2"] += 1
            elif m.score >= 0.8:
                bucket["0.8-1.0"] += 1
            else:
                bucket["<0.8"] += 1
        print("\nScore distribution:", file=sys.stderr)
        for k in ("1.4+", "1.2-1.4", "1.0-1.2", "0.8-1.0", "<0.8"):
            print(f"  {k:<10} {bucket[k]:,}", file=sys.stderr)

        country_bucket = Counter(m.temple_country or "(none)" for m in matches)
        print("\nMatches by temple country:", file=sys.stderr)
        for c, n in country_bucket.most_common():
            print(f"  {c:<20} {n:,}", file=sys.stderr)

        # Sample CSV for human review
        if sample_csv or not write:
            sample = matches if len(matches) <= sample_size else random.sample(matches, sample_size)
            out = sys.stdout if not sample_csv else open(sample_csv, "w", newline="", encoding="utf-8")
            try:
                writer = csv.writer(out)
                writer.writerow([
                    "person_id", "person_name", "dynasty", "temple_name",
                    "temple_country", "lat", "lng", "score", "same_name_count", "reason",
                ])
                for m in sample:
                    writer.writerow([
                        m.person_id, m.person_name, m.person_dynasty or "",
                        m.temple_name, m.temple_country or "",
                        m.temple_lat, m.temple_lng, f"{m.score:.2f}",
                        m.same_name_count, m.reason,
                    ])
            finally:
                if sample_csv:
                    out.close()
                    print(f"\nSample CSV written: {sample_csv}", file=sys.stderr)

        if not write:
            print("\n(dry-run; no DB writes)", file=sys.stderr)
            return

        # Write to DB
        print(f"\nWriting {len(matches):,} matches to DB...", file=sys.stderr)
        written = 0
        for m in matches:
            geo_source = f"desc_match_v3:{m.temple_country or 'CN'}:{m.temple_name}:{m.score:.2f}"
            result = await session.execute(
                text(
                    """
                    UPDATE kg_entities
                    SET properties = (
                        properties::jsonb || jsonb_build_object(
                            'latitude',   cast(:lat AS text),
                            'longitude',  cast(:lng AS text),
                            'geo_source', cast(:gs  AS text)
                        )
                    )::json
                    WHERE id = :pid
                      AND entity_type = 'person'
                      AND (
                        (properties->>'latitude') IS NULL
                        OR properties->>'geo_source' LIKE 'desc_match:%'
                      )
                    """
                ),
                {"lat": str(m.temple_lat), "lng": str(m.temple_lng), "gs": geo_source, "pid": m.person_id},
            )
            written += result.rowcount or 0
        await session.commit()
        print(f"Done. {written:,} rows updated.", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="actually write to DB")
    ap.add_argument("--dry-run", action="store_true", help="default; alias for not passing --write")
    ap.add_argument("--min-score", type=float, default=0.5, help="reject matches below this score")
    ap.add_argument("--sample", type=int, default=100, help="how many sample rows to emit")
    ap.add_argument("--sample-csv", type=str, default=None, help="write sample to CSV file instead of stdout")
    args = ap.parse_args()

    asyncio.run(
        run(
            write=args.write,
            min_score=args.min_score,
            sample_size=args.sample,
            sample_csv=args.sample_csv,
        )
    )


if __name__ == "__main__":
    main()
