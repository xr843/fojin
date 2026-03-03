import json

import httpx
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.iiif import IIIFManifest

MANIFEST_CACHE_TTL = 3600  # 1 hour


async def get_text_manifests(session: AsyncSession, text_id: int) -> list[IIIFManifest]:
    result = await session.execute(
        select(IIIFManifest).where(IIIFManifest.text_id == text_id)
    )
    return list(result.scalars().all())


async def get_manifest_by_id(session: AsyncSession, manifest_id: int) -> IIIFManifest | None:
    return await session.get(IIIFManifest, manifest_id)


async def get_manifest_json(
    session: AsyncSession, manifest_id: int, redis_client: aioredis.Redis | None = None
) -> dict | None:
    """Get manifest JSON, with Redis caching for external manifests."""
    manifest = await session.get(IIIFManifest, manifest_id)
    if not manifest:
        return None

    # If we have cached JSON in DB, return it
    if manifest.manifest_json:
        return manifest.manifest_json

    cache_key = f"iiif:manifest:{manifest_id}"

    # Check Redis cache
    if redis_client:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)

    # Fetch from external URL
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(manifest.manifest_url)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    # Cache in Redis
    if redis_client:
        await redis_client.setex(cache_key, MANIFEST_CACHE_TTL, json.dumps(data))

    return data


def generate_bdrc_manifest_url(work_id: str) -> str:
    """Generate a IIIF manifest URL for a BDRC work."""
    return f"https://iiifpres.bdrc.io/2.1.1/v:bdr:{work_id}/manifest"
