"""Sync cbeta_gaiji corpus into the local gaiji table.

The gaiji table schema is created by alembic 0150; this script does
the initial population AND any subsequent re-syncs when upstream
(github.com/cbeta-org/cbeta_gaiji) ships changes. The 4MB JSON
snapshot is intentionally not committed (matches fojin's data/
gitignore convention) — we fetch from upstream at run time and
record the resolved commit SHA in upstream_version.

Usage:
    cd backend
    python scripts/import_gaiji.py [--ref master|<sha>] [--dry-run]
                                   [--from-file path]

  --ref       Git ref to fetch from upstream (default: master).
  --dry-run   Parse + report row deltas without writing.
  --from-file Use a local JSON snapshot instead of fetching upstream.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Match fojin/backend/scripts/audit_*.py convention: inject backend/
# onto sys.path so `from app.…` resolves when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.gaiji import Gaiji  # noqa: E402

UPSTREAM_URL = "https://raw.githubusercontent.com/cbeta-org/cbeta_gaiji/{ref}/cbeta_gaiji.json"
COMMIT_API = "https://api.github.com/repos/cbeta-org/cbeta_gaiji/commits/{ref}"


def _map_entry(cb_code: str, entry: dict, upstream_version: str) -> dict:
    raw_unicode = entry.get("unicode")
    return {
        "cb_code": cb_code,
        "composition": entry.get("composition"),
        "unicode_char": entry.get("uni_char"),
        "unicode_codepoint": f"U+{raw_unicode}" if raw_unicode else None,
        "norm_unicode_char": entry.get("norm_uni_char") or entry.get("norm_unicode"),
        "norm_big5_char": entry.get("norm_big5_char"),
        "pua_codepoint": entry.get("pua"),
        "moe_variant_id": entry.get("moe_variant_id"),
        "source": "cbeta",
        "upstream_version": upstream_version,
    }


async def _resolve_upstream_sha(ref: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(COMMIT_API.format(ref=ref))
        r.raise_for_status()
        return r.json()["sha"][:8]


async def _fetch_upstream(ref: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(UPSTREAM_URL.format(ref=ref))
        r.raise_for_status()
        return r.json()


async def _upsert(rows: list[dict]) -> tuple[int, int]:
    """Returns (rows_processed, existing_rows_before_run)."""
    async with async_session() as db:
        existing = (await db.execute(select(func.count(Gaiji.id)))).scalar_one()
        # Chunk to keep single statements modest; 31k rows is fine for one
        # query but ON CONFLICT planning gets cheaper in batches.
        for start in range(0, len(rows), 2000):
            chunk = rows[start : start + 2000]
            stmt = pg_insert(Gaiji).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["cb_code"],
                set_={
                    "composition": stmt.excluded.composition,
                    "unicode_char": stmt.excluded.unicode_char,
                    "unicode_codepoint": stmt.excluded.unicode_codepoint,
                    "norm_unicode_char": stmt.excluded.norm_unicode_char,
                    "norm_big5_char": stmt.excluded.norm_big5_char,
                    "pua_codepoint": stmt.excluded.pua_codepoint,
                    "moe_variant_id": stmt.excluded.moe_variant_id,
                    "upstream_version": stmt.excluded.upstream_version,
                    "updated_at": func.now(),
                },
            )
            await db.execute(stmt)
        await db.commit()
        return len(rows), existing


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="master")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-file", type=Path)
    args = parser.parse_args()

    if args.from_file:
        data = json.loads(args.from_file.read_text(encoding="utf-8"))
        upstream_version = f"file:{args.from_file.name}"
    else:
        upstream_version = await _resolve_upstream_sha(args.ref)
        data = await _fetch_upstream(args.ref)

    rows = [_map_entry(cb, entry, upstream_version) for cb, entry in data.items()]
    print(f"parsed {len(rows)} entries @ upstream {upstream_version}")

    if args.dry_run:
        print("dry-run: no writes")
        return 0

    processed, existing_before = await _upsert(rows)
    print(f"upserted {processed} rows (existing before: {existing_before})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
