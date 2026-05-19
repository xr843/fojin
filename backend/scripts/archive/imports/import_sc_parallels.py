"""
Import SuttaCentral parallel text relations (Pali ↔ Chinese) from offline data.

Uses the parallels.json file from https://github.com/suttacentral/sc-data/blob/main/relationship/parallels.json
instead of hitting the API per-text, which is much faster and more complete.

Mapping logic:
  - SC Pali IDs (dn1, mn1, sn1.1, an1.1, ...) → our cbeta_id SC-{uid} (SC-dn1, SC-mn1, ...)
  - SC Chinese IDs:
    - t{num} / t{num}.{sub} → CBETA T{num:04d} (e.g., t10 → T0010, t210.10 → T0210)
    - da{num} → T0001 (長阿含經 Dīrghāgama)
    - ma{num} → T0026 (中阿含經 Madhyamāgama)
    - sa{num} → T0099 (雜阿含經 Saṃyuktāgama)
    - sa-2.{num} → T0100 (別譯雜阿含經)
    - ea{num} → T0125 (增壹阿含經 Ekottarāgama)

Usage:
    # Dry run (default): show stats only, no DB changes
    python scripts/import_sc_parallels.py

    # Actually import into DB
    python scripts/import_sc_parallels.py --execute

    # Re-download parallels.json from GitHub
    python scripts/import_sc_parallels.py --download --execute
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

PARALLELS_URL = "https://raw.githubusercontent.com/suttacentral/sc-data/main/relationship/parallels.json"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PARALLELS_FILE = DATA_DIR / "sc_parallels.json"

# Pali nikaya prefixes used in SuttaCentral
PALI_PREFIXES = (
    "dn", "mn", "sn", "an",
    "kp", "dhp", "ud", "iti", "snp",
    "vv", "pv", "thag", "thig",
    "ja", "ne", "cnd", "mnd", "ps",
    "mil", "pe",
    "pli-tv",
)

# Agama collection mappings: SC prefix → CBETA T-number
AGAMA_MAP = {
    "da": "T0001",   # 長阿含經 Dīrghāgama
    "ma": "T0026",   # 中阿含經 Madhyamāgama
    "sa": "T0099",   # 雜阿含經 Saṃyuktāgama
    "sa-2": "T0100", # 別譯雜阿含經
    "ea": "T0125",   # 增壹阿含經 Ekottarāgama
}


def is_pali_id(sc_id: str) -> bool:
    """Check if a SuttaCentral ID is a Pali nikaya text."""
    for prefix in PALI_PREFIXES:
        if sc_id == prefix:
            return True
        if sc_id.startswith(prefix):
            rest = sc_id[len(prefix):]
            if rest and (rest[0].isdigit() or rest[0] in (".", "-")):
                return True
    return False


def sc_chinese_to_cbeta(sc_id: str) -> str | None:
    """
    Convert a SuttaCentral Chinese text ID to a CBETA T-number.

    Examples:
        t10 → T0010
        t210.10 → T0210
        t132a → T0132
        da1 → T0001
        ma55 → T0026
        sa100 → T0099
        sa-2.180 → T0100
        ea1.1 → T0125
    """
    # Handle t-prefix (individual Taisho texts)
    m = re.match(r"^t(\d+)", sc_id)
    if m:
        num = m.group(1)
        return f"T{num.zfill(4)}"

    # Handle sa-2 (別譯雜阿含) before sa
    if re.match(r"^sa-2\b", sc_id):
        return "T0100"

    # Handle agama prefixes
    for prefix, cbeta_id in AGAMA_MAP.items():
        if prefix == "sa-2":
            continue  # already handled above
        if re.match(rf"^{prefix}\d", sc_id):
            return cbeta_id

    return None


def sc_pali_to_cbeta(sc_id: str) -> str:
    """Convert a Pali SC ID to our cbeta_id format: SC-{uid}."""
    return f"SC-{sc_id}"


def parse_sutta_number(cbeta_id: str) -> tuple[str, int | None, int | None]:
    """
    Parse a cbeta_id like 'SC-an1.51-60' into (prefix, start, end).
    Returns (prefix, start_num, end_num) or (prefix, single_num, single_num).
    For IDs without numbers, returns (cbeta_id, None, None).

    Handles formats:
        SC-an1.51-60   → ('SC-an1.', 51, 60)
        SC-an1.56      → ('SC-an1.', 56, 56)
        SC-dhp1-20     → ('SC-dhp', 1, 20)
        SC-dhp71       → ('SC-dhp', 71, 71)
        SC-dn1         → ('SC-dn', 1, 1)
        SC-thag1.1     → ('SC-thag', 1.1) — handled as dot-prefix
        SC-sn23.35-45  → ('SC-sn23.', 35, 45)
    """
    # Match patterns like SC-an1.51-60, SC-an10.156-166, SC-sn1.1
    m = re.match(r"^(SC-[a-z]+\d*\.)(\d+)(?:-(\d+))?$", cbeta_id)
    if m:
        prefix = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        return prefix, start, end

    # Match patterns like SC-dhp1-20, SC-dhp71, SC-dn1, SC-mn1 (no dot, alpha prefix + number)
    m = re.match(r"^(SC-[a-z]+)(\d+)(?:-(\d+))?$", cbeta_id)
    if m:
        prefix = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        return prefix, start, end

    return cbeta_id, None, None


def build_range_index(pali_map: dict[str, int]) -> dict[str, list[tuple[int, int, int]]]:
    """
    Build an index for range-based Pali text matching.
    Returns {prefix: [(start, end, db_id), ...]} sorted by start.
    """
    index = defaultdict(list)
    for cbeta_id, db_id in pali_map.items():
        prefix, start, end = parse_sutta_number(cbeta_id)
        if start is not None:
            index[prefix].append((start, end, db_id))

    # Sort each prefix's ranges by start
    for prefix in index:
        index[prefix].sort()

    return index


def resolve_pali_id(
    pali_cbeta: str,
    pali_map: dict[str, int],
    range_index: dict[str, list[tuple[int, int, int]]],
) -> int | None:
    """
    Resolve a Pali cbeta_id to a DB id, with range-overlap fallback.

    If 'SC-an1.56' is not in pali_map directly, check if it falls within
    a range like 'SC-an1.51-60' using the range_index.
    """
    # Direct lookup
    db_id = pali_map.get(pali_cbeta)
    if db_id:
        return db_id

    # Range overlap lookup
    prefix, start, end = parse_sutta_number(pali_cbeta)
    if start is None:
        return None

    ranges = range_index.get(prefix, [])
    for r_start, r_end, r_db_id in ranges:
        # Check if any part of [start, end] overlaps with [r_start, r_end]
        if start <= r_end and end >= r_start:
            return r_db_id

    return None


def extract_parallel_pairs(data: list[dict]) -> list[tuple[str, str, str, str]]:
    """
    Extract (pali_cbeta_id, chinese_cbeta_id, sc_pali_uid, sc_chinese_uid) pairs
    from SuttaCentral parallels.json data.
    """
    pairs = set()

    for entry in data:
        if "parallels" not in entry:
            continue

        raw_ids = entry["parallels"]
        # Parse IDs: strip fragment (#...) and approximate marker (~)
        parsed = []
        for raw in raw_ids:
            base_id = raw.split("#")[0].lstrip("~")
            parsed.append(base_id)

        # Classify each ID
        pali_ids = [i for i in parsed if is_pali_id(i)]
        chinese_ids = []
        for i in parsed:
            cbeta = sc_chinese_to_cbeta(i)
            if cbeta:
                chinese_ids.append((i, cbeta))

        # Create pairs
        for pi in pali_ids:
            pali_cbeta = sc_pali_to_cbeta(pi)
            for sc_zh, zh_cbeta in chinese_ids:
                pairs.add((pali_cbeta, zh_cbeta, pi, sc_zh))

    return sorted(pairs)


async def download_parallels():
    """Download parallels.json from SuttaCentral GitHub."""
    print(f"Downloading parallels.json from {PARALLELS_URL}...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(PARALLELS_URL)
        resp.raise_for_status()
        PARALLELS_FILE.write_bytes(resp.content)

    print(f"  Saved to {PARALLELS_FILE} ({len(resp.content):,} bytes)")


async def run(execute: bool = False, download: bool = False):
    """Main import logic."""
    # Step 1: Ensure parallels data exists
    if download or not PARALLELS_FILE.exists():
        await download_parallels()

    if not PARALLELS_FILE.exists():
        print(f"ERROR: {PARALLELS_FILE} not found. Run with --download first.")
        sys.exit(1)

    # Step 2: Parse parallels data
    print(f"\nLoading {PARALLELS_FILE}...")
    with open(PARALLELS_FILE) as f:
        data = json.load(f)
    print(f"  {len(data)} entries in parallels.json")

    # Step 3: Extract Pali ↔ Chinese pairs
    pairs = extract_parallel_pairs(data)
    print(f"  {len(pairs)} Pali ↔ Chinese parallel pairs extracted")

    # Unique counts
    unique_pali = set(p[0] for p in pairs)
    unique_chinese = set(p[1] for p in pairs)
    print(f"  Unique Pali texts: {len(unique_pali)}")
    print(f"  Unique Chinese texts: {len(unique_chinese)}")

    # Breakdown by Chinese text type
    direct_t = [(p, c) for p, c, _, _ in pairs if c not in AGAMA_MAP.values()]
    agama = [(p, c) for p, c, _, _ in pairs if c in AGAMA_MAP.values()]
    print(f"  Direct T-number pairs: {len(direct_t)}")
    print(f"  Agama collection pairs: {len(agama)}")

    # Step 4: Connect to DB and resolve IDs
    print("\nConnecting to database...")
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # Load all Pali text IDs
            result = await session.execute(
                text("SELECT id, cbeta_id FROM buddhist_texts WHERE lang = 'pi'")
            )
            pali_map = {row.cbeta_id: row.id for row in result.fetchall()}
            print(f"  Pali texts in DB: {len(pali_map)}")

            # Load all Chinese text IDs
            result = await session.execute(
                text("SELECT id, cbeta_id FROM buddhist_texts WHERE lang = 'lzh'")
            )
            chinese_map = {row.cbeta_id: row.id for row in result.fetchall()}
            print(f"  Chinese texts in DB: {len(chinese_map)}")

            # Load existing relations to avoid duplicates
            result = await session.execute(
                text("""
                    SELECT text_a_id, text_b_id FROM text_relations
                    WHERE relation_type = 'parallel' AND source = 'suttacentral'
                """)
            )
            existing = {(row.text_a_id, row.text_b_id) for row in result.fetchall()}
            print(f"  Existing SC parallel relations: {len(existing)}")

        # Build range index for fuzzy Pali matching
        range_index = build_range_index(pali_map)

        # Step 5: Match pairs to DB IDs
        matched = []
        unmatched_pali = set()
        unmatched_chinese = set()

        for pali_cbeta, zh_cbeta, sc_pali, sc_zh in pairs:
            pali_id = resolve_pali_id(pali_cbeta, pali_map, range_index)
            zh_id = chinese_map.get(zh_cbeta)

            if not pali_id:
                unmatched_pali.add(pali_cbeta)
                continue
            if not zh_id:
                unmatched_chinese.add(zh_cbeta)
                continue

            # Normalize order: smaller ID first
            a_id, b_id = (pali_id, zh_id) if pali_id < zh_id else (zh_id, pali_id)

            if (a_id, b_id) not in existing:
                note = f"SC: {sc_pali} ↔ {sc_zh}"
                matched.append((a_id, b_id, note))

        # Deduplicate matched pairs (same DB IDs may come from different SC sub-IDs)
        unique_matched = {}
        for a_id, b_id, note in matched:
            key = (a_id, b_id)
            if key not in unique_matched:
                unique_matched[key] = note
            else:
                # Append note if different
                if note not in unique_matched[key]:
                    unique_matched[key] += f"; {note}"

        print(f"\n{'=' * 60}")
        print("RESULTS:")
        print(f"  Pairs to insert: {len(unique_matched)}")
        print(f"  Already existing: {len(existing)}")
        print(f"  Unmatched Pali texts: {len(unmatched_pali)}")
        print(f"  Unmatched Chinese texts: {len(unmatched_chinese)}")

        if unmatched_chinese:
            print(f"\n  Unmatched Chinese CBETA IDs: {sorted(unmatched_chinese)[:20]}")
        if unmatched_pali and len(unmatched_pali) <= 20:
            print(f"  Unmatched Pali CBETA IDs (sample): {sorted(unmatched_pali)[:20]}")
        elif unmatched_pali:
            print(f"  Unmatched Pali CBETA IDs: {len(unmatched_pali)} (too many to list)")

        # Show sample matches
        print("\n  Sample matches:")
        sample_items = list(unique_matched.items())[:10]
        if sample_items:
            async with session_factory() as session:
                for (a_id, b_id), _note in sample_items:
                    result = await session.execute(
                        text("""
                            SELECT a.cbeta_id as a_cbeta, a.title_zh as a_title,
                                   b.cbeta_id as b_cbeta, b.title_zh as b_title
                            FROM buddhist_texts a, buddhist_texts b
                            WHERE a.id = :a_id AND b.id = :b_id
                        """),
                        {"a_id": a_id, "b_id": b_id},
                    )
                    row = result.fetchone()
                    if row:
                        print(f"    {row.a_cbeta} ({row.a_title}) ↔ {row.b_cbeta} ({row.b_title})")

        # Step 6: Execute INSERT if requested
        if execute and unique_matched:
            print(f"\n{'=' * 60}")
            print(f"Inserting {len(unique_matched)} parallel relations...")

            inserted = 0
            skipped = 0
            async with session_factory() as session:
                for i, ((a_id, b_id), note) in enumerate(unique_matched.items()):
                    try:
                        await session.execute(
                            text("""
                                INSERT INTO text_relations
                                    (text_a_id, text_b_id, relation_type, source, confidence, note)
                                VALUES (:a, :b, 'parallel', 'suttacentral', 0.9, :note)
                                ON CONFLICT ON CONSTRAINT uq_text_relation DO NOTHING
                            """),
                            {"a": a_id, "b": b_id, "note": note},
                        )
                        inserted += 1
                    except Exception as e:
                        print(f"  Error inserting ({a_id}, {b_id}): {e}")
                        skipped += 1

                    if (i + 1) % 500 == 0:
                        await session.commit()
                        print(f"  Progress: {i + 1}/{len(unique_matched)}")

                await session.commit()

            print(f"  Inserted: {inserted}, Skipped: {skipped}")
        elif not execute:
            print("\n  DRY RUN — use --execute to actually insert into DB")

    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(
        description="Import SuttaCentral Pali ↔ Chinese parallel text relations"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually insert relations into DB (default: dry run)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="(Re-)download parallels.json from GitHub",
    )
    args = parser.parse_args()

    asyncio.run(run(execute=args.execute, download=args.download))


if __name__ == "__main__":
    main()
