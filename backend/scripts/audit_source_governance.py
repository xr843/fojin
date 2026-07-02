"""Audit source health, ingest coverage, and license metadata gaps.

Usage:
    cd backend
    python -m scripts.audit_source_governance
    python -m scripts.audit_source_governance --json
"""

from __future__ import annotations

import argparse
import asyncio
import json


def _print_text(report: dict) -> None:
    print("FoJin source governance audit")
    print("=" * 34)
    print(f"active sources:              {report['total_active']}")
    print(f"health status counts:        {report['health_status_counts']}")
    print(f"health review queue:         {len(report['health_review_codes'])}")
    print(f"license review queue:        {len(report['license_review_codes'])}")
    print(f"catalog-only sources:        {len(report['catalog_only_codes'])}")
    print(f"fulltext-capable sources:    {report['local_or_remote_fulltext_count']}")
    print(f"primary ingest sources:      {report['primary_ingest_count']}")
    print(f"missing SPDX count:          {report['missing_license_spdx_count']}")
    print(f"missing license verified:    {report['missing_license_verified_count']}")
    print(f"embedding unknown count:     {report['embedding_unknown_count']}")
    print(f"redistribution unknown count:{report['redistribution_unknown_count']}")

    for title, key in [
        ("Health review codes", "health_review_codes"),
        ("License review codes", "license_review_codes"),
        ("Missing primary ingest codes", "missing_primary_ingest_codes"),
        ("Catalog-only codes", "catalog_only_codes"),
    ]:
        codes = report[key]
        print(f"\n{title} ({len(codes)}):")
        print("  " + ", ".join(codes) if codes else "  none")


async def _load_report() -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.services.source import get_all_sources
    from app.services.source_governance import build_source_governance_report

    engine = create_async_engine(settings.database_url)
    try:
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            sources = await get_all_sources(session, active_only=True)
        return build_source_governance_report(sources)
    finally:
        await engine.dispose()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    report = await _load_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(report)


if __name__ == "__main__":
    asyncio.run(main())
