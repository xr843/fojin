"""The streamed answer's latency reaches persist_answer_diagnostic (migration 0182).

Before this, 首字/总耗时 existed only in the browser and in ~10 hours of rotating
container logs, so "did answers get slower?" had no answer at all.
"""

from tests.test_chat_stream_endpoint_integration import (
    _make_mock_httpx_client,
    _make_prepare_return,
    _make_sources,
    _stream_patches,
)


async def test_stream_passes_sane_timing_to_diagnostics(client):
    p1, p2, p3, p4, p5, p6 = _stream_patches(
        _make_prepare_return(_make_sources()), _make_mock_httpx_client(["般", "若"])
    )
    with p1, p2, p3, p4 as persist_mock, p5, p6:
        resp = await client.post("/api/chat/stream", json={"message": "什么是般若？"})
    assert resp.status_code == 200
    persist_mock.assert_awaited_once()
    timing = persist_mock.await_args.kwargs["timing"]
    assert timing is not None
    assert all(isinstance(v, int) for v in (timing.prep_ms, timing.first_token_ms, timing.total_ms))
    assert 0 <= timing.prep_ms <= timing.first_token_ms <= timing.total_ms
    assert timing.model == "test-model"
