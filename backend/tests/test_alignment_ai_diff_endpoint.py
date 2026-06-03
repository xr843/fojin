from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_ai_diff_returns_analysis(client):
    """Endpoint returns analysis from cache or fresh LLM call."""
    body = {
        "chunks": [
            {"text_id": 100, "juan_num": 1, "chunk_index": 0, "lang": "lzh", "text": "觀自在菩薩。"},
            {"text_id": 200, "juan_num": 1, "chunk_index": 0, "lang": "en", "text": "Avalokiteshvara Bodhisattva."},
        ]
    }
    fake_analysis = {
        "summary": "中英两版核心一致。",
        "differences": ["lzh 用观自在，en 用 Avalokiteshvara 音译"],
        "doctrinal_notes": "",
    }
    with patch(
        "app.api.alignment.get_or_create_diff",
        new=AsyncMock(return_value=(False, "v1", "deepseek-v4-pro", fake_analysis)),
    ):
        resp = await client.post("/api/alignment/ai-diff", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["cached"] is False
    assert data["prompt_version"] == "v1"
    assert data["model"] == "deepseek-v4-pro"
    assert data["analysis"]["summary"] == "中英两版核心一致。"


@pytest.mark.asyncio
async def test_ai_diff_rejects_too_few_chunks(client):
    body = {"chunks": [{"text_id": 100, "juan_num": 1, "chunk_index": 0, "lang": "lzh", "text": "x"}]}
    resp = await client.post("/api/alignment/ai-diff", json=body)
    assert resp.status_code == 422  # pydantic min_length=2


@pytest.mark.asyncio
async def test_ai_diff_rejects_too_many_chunks(client):
    body = {
        "chunks": [
            {"text_id": i, "juan_num": 1, "chunk_index": 0, "lang": "lzh", "text": "x"} for i in range(5)
        ]
    }
    resp = await client.post("/api/alignment/ai-diff", json=body)
    assert resp.status_code == 422
