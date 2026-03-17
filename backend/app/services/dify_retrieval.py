import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def dify_dataset_search(query: str, top_k: int = 3) -> list[dict]:
    """Search Dify knowledge base datasets via the Dataset API.

    Returns a list of dicts with keys: chunk_text, score, dataset_id.
    Silently returns [] if Dify is not configured or all requests fail.
    """
    if not settings.dify_api_url or not settings.dify_dataset_api_key:
        return []

    dataset_ids = [
        did.strip()
        for did in settings.dify_dataset_ids.split(",")
        if did.strip()
    ]
    if not dataset_ids:
        return []

    results: list[dict] = []
    async with httpx.AsyncClient(timeout=2) as client:
        for dataset_id in dataset_ids:
            try:
                resp = await client.post(
                    f"{settings.dify_api_url}/datasets/{dataset_id}/retrieve",
                    headers={
                        "Authorization": f"Bearer {settings.dify_dataset_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": query,
                        "retrieve_strategy": "single",
                        "single": {"top_k": top_k},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                for record in data.get("records", []):
                    segment = record.get("segment", {})
                    results.append({
                        "chunk_text": segment.get("content", ""),
                        "score": record.get("score", 0.0),
                        "dataset_id": dataset_id,
                    })
            except Exception:
                logger.warning(
                    "Dify dataset search failed for %s, skipping",
                    dataset_id,
                    exc_info=True,
                )
    return results
