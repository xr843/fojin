"""Import BDRC IIIF manifests by querying their SPARQL endpoint for Taisho correspondences."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import select

from app.database import async_session
from app.models.source import DataSource
from app.models.text import BuddhistText
from app.models.iiif import IIIFManifest

BDRC_SPARQL = "https://ldspdi.bdrc.io/query/graph/Taisho_to_BDRC"


async def main():
    async with async_session() as session:
        # Get BDRC source
        result = await session.execute(
            select(DataSource).where(DataSource.code == "bdrc")
        )
        bdrc_source = result.scalar_one_or_none()
        if not bdrc_source:
            print("ERROR: BDRC data source not found. Run migration 0007 first.")
            return

        # Try to query BDRC SPARQL for Taisho-to-BDRC mappings
        print("Querying BDRC for Taisho-to-BDRC mappings...")
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(
                    BDRC_SPARQL,
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            print(f"BDRC SPARQL query failed: {e}")
            print("Creating sample manifests for demonstration...")
            await create_sample_manifests(session, bdrc_source)
            return

        # Process SPARQL results
        bindings = data.get("results", {}).get("bindings", [])
        count = 0
        for binding in bindings:
            taisho_id = binding.get("taishoId", {}).get("value", "")
            work_uri = binding.get("work", {}).get("value", "")
            if not taisho_id or not work_uri:
                continue

            work_id = work_uri.split("/")[-1]

            # Find matching text
            text_result = await session.execute(
                select(BuddhistText).where(BuddhistText.taisho_id == taisho_id)
            )
            text = text_result.scalar_one_or_none()
            if not text:
                continue

            # Check for existing manifest
            existing = await session.execute(
                select(IIIFManifest).where(
                    IIIFManifest.text_id == text.id,
                    IIIFManifest.source_id == bdrc_source.id,
                )
            )
            if existing.scalar_one_or_none():
                continue

            manifest = IIIFManifest(
                text_id=text.id,
                source_id=bdrc_source.id,
                label=f"BDRC: {text.title_zh}",
                manifest_url=f"https://iiifpres.bdrc.io/2.1.1/v:bdr:{work_id}/manifest",
                provider="bdrc",
                rights="CC BY-NC 4.0",
            )
            session.add(manifest)
            count += 1

        await session.commit()
        print(f"Imported {count} BDRC manifests.")


async def create_sample_manifests(session, bdrc_source):
    """Create sample manifests for first few texts (for demo/development)."""
    result = await session.execute(
        select(BuddhistText).where(BuddhistText.taisho_id.isnot(None)).limit(5)
    )
    texts = result.scalars().all()

    count = 0
    for text in texts:
        existing = await session.execute(
            select(IIIFManifest).where(
                IIIFManifest.text_id == text.id,
                IIIFManifest.source_id == bdrc_source.id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        manifest = IIIFManifest(
            text_id=text.id,
            source_id=bdrc_source.id,
            label=f"BDRC: {text.title_zh}",
            manifest_url=f"https://iiifpres.bdrc.io/2.1.1/v:bdr:W{text.taisho_id}/manifest",
            provider="bdrc",
            rights="CC BY-NC 4.0",
        )
        session.add(manifest)
        count += 1

    await session.commit()
    print(f"Created {count} sample BDRC manifests.")


if __name__ == "__main__":
    asyncio.run(main())
