"""Integration test for the full ``POST /api/chat/stream`` HTTP path.

The existing stream tests (``test_chat_stream_session_lifecycle``,
``test_chat_sources_order``, …) call ``send_message_stream`` directly, so the
*endpoint* layer — bearer-token parsing, ``StreamingResponse`` wiring, SSE
headers, and the actual bytes a client receives — was exercised by nothing
before merge. This suite drives the real route through ASGI and asserts the
wire protocol end to end:

    padding-comment → searching → session_id → token* →
    [citation_correction] → trust_status → sources → message_id → done

Mocking happens only at the outermost boundaries (same seams as the unit
tests): ``_prepare_chat`` (needs PG/Redis), the LLM's ``httpx.AsyncClient``,
and the persistence helpers. The generator body, the endpoint, the citation
guard, the quote verifier, and trust-status assembly all run for real.

``send_message_stream`` binds its DB factory as a *default argument*
(``sessionmaker=async_session``), which is evaluated at import time — patching
``app.services.chat.async_session`` would silently not take. The injection
seam is the endpoint module's reference instead: replace
``app.api.chat.send_message_stream`` with ``functools.partial(real,
sessionmaker=fake)`` so the real generator runs with a test session factory.
"""

import json
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import QuotaExceededError
from app.core.metrics import CITATION_GUARD_MUTATIONS_TOTAL
from app.schemas.chat import ChatSource
from app.services.chat import send_message_stream


def _make_sources() -> list[ChatSource]:
    return [
        ChatSource(text_id=1, juan_num=1, chunk_text="色不异空", score=0.9, title_zh="心经"),
    ]


def _make_prepare_return(sources: list[ChatSource]):
    fake_session = MagicMock()
    fake_session.id = 42
    llm_messages = [{"role": "user", "content": "测试"}]
    return (
        fake_session, "https://api.example.com/v1", "fake-key", "test-model",
        False, "openai", sources, llm_messages, [],
    )


def _make_mock_httpx_client(tokens: list[str]):
    """OpenAI-style streaming mock — same shape as the unit-test suites."""
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}" for t in tokens]
    lines.append("data: [DONE]")
    mock_resp = MagicMock()

    async def aiter_lines():
        for line in lines:
            yield line

    mock_resp.aiter_lines = aiter_lines
    mock_resp.raise_for_status = MagicMock()

    class _StreamCM:
        async def __aenter__(self):
            return mock_resp

        async def __aexit__(self, *_):
            return False

    class _ClientInstance:
        def stream(self, *args, **kwargs):
            return _StreamCM()

    class _ClientCM:
        async def __aenter__(self):
            return _ClientInstance()

        async def __aexit__(self, *_):
            return False

    return MagicMock(return_value=_ClientCM())


class _FakeSessionmaker:
    """``async with sessionmaker() as db`` → fresh AsyncMock per phase."""

    def __call__(self):
        class _CM:
            async def __aenter__(self):
                return AsyncMock()

            async def __aexit__(self, *_):
                return False

        return _CM()


def _parse_sse(raw: str) -> tuple[list[dict], list[str]]:
    """Split an SSE body into (json events, comment frames)."""
    events, comments = [], []
    for frame in raw.split("\n\n"):
        if not frame.strip():
            continue
        if frame.startswith(":"):
            comments.append(frame)
        elif frame.startswith("data: "):
            events.append(json.loads(frame[len("data: "):]))
    return events, comments


def _stream_patches(prepare, httpx_client, save_id=77):
    return (
        patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare),
        patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=save_id),
        patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock),
        patch("app.services.chat.persist_answer_diagnostic", new_callable=AsyncMock),
        patch("app.services.chat.httpx.AsyncClient", httpx_client),
        patch(
            "app.api.chat.send_message_stream",
            new=partial(send_message_stream, sessionmaker=_FakeSessionmaker()),
        ),
    )


async def test_stream_endpoint_full_event_sequence(client):
    """Anonymous POST /api/chat/stream → complete happy-path SSE protocol."""
    p1, p2, p3, p4, p5, p6 = _stream_patches(
        _make_prepare_return(_make_sources()), _make_mock_httpx_client(["般", "若"])
    )
    with p1, p2 as save_mock, p3, p4, p5, p6:
        resp = await client.post("/api/chat/stream", json={"message": "什么是般若？"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "no-cache" in resp.headers["cache-control"]
    assert resp.headers.get("x-accel-buffering") == "no"

    events, comments = _parse_sse(resp.text)
    # Cloudflare buffer-flush padding is the very first frame on the wire.
    assert comments and len(comments[0]) >= 2048

    types = [e["type"] for e in events]
    assert types == [
        "searching", "session_id", "token", "token",
        "trust_status", "sources", "message_id", "done",
    ], f"unexpected SSE sequence: {types}"

    by_type = {e["type"]: e for e in events}
    assert by_type["session_id"]["session_id"] == 42
    assert [e["content"] for e in events if e["type"] == "token"] == ["般", "若"]
    assert by_type["sources"]["sources"][0]["title_zh"] == "心经"
    # message_id is the persisted chat_messages.id (frontend swaps its
    # Date.now() placeholder with it — feedback buttons PUT to this id).
    assert by_type["message_id"]["id"] == 77
    save_mock.assert_awaited_once()


async def test_stream_endpoint_citation_guard_rewrites_on_the_wire(client):
    """A hallucinated 【《X》第N卷】 citation must be stripped before persist,
    surface as a citation_correction event, and increment the guard metric."""
    tokens = ["根据【《伪造经》第9卷】，", "色即是空。"]
    counter = CITATION_GUARD_MUTATIONS_TOTAL.labels(kind="unverified_title")
    before = counter._value.get()

    p1, p2, p3, p4, p5, p6 = _stream_patches(
        _make_prepare_return(_make_sources()), _make_mock_httpx_client(tokens)
    )
    with p1, p2 as save_mock, p3, p4, p5, p6:
        resp = await client.post("/api/chat/stream", json={"message": "引用测试"})

    events, _ = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "citation_correction" in types, f"guard event missing: {types}"
    assert types[-1] == "done"
    # citation_correction must arrive AFTER all tokens (frontend swaps the
    # visible message; a later raw token would re-introduce the hallucination).
    assert types.index("citation_correction") > types.index("token", 1)

    corrected = next(e for e in events if e["type"] == "citation_correction")["content"]
    assert "【" not in corrected  # clickable wrapper stripped
    assert "伪造经" in corrected  # prose mention retained

    # The persisted answer is the corrected one, not the raw LLM output.
    saved_answer = save_mock.await_args.args[3]
    assert "【" not in saved_answer

    # P0-1 metric: the rewrite is observable in /metrics, not just logs.
    assert counter._value.get() == before + 1


async def test_stream_endpoint_prep_rejection_yields_error_then_done(client):
    """App-level rejection (e.g. quota) → error + done; stream never opens."""
    p1, p2, p3, p4, p5, p6 = _stream_patches(
        _make_prepare_return(_make_sources()), _make_mock_httpx_client(["x"])
    )
    with p1 as prep_mock, p2, p3, p4, p5, p6:
        prep_mock.side_effect = QuotaExceededError("今日免费额度已用完")
        resp = await client.post("/api/chat/stream", json={"message": "超额测试"})

    assert resp.status_code == 200  # SSE transport succeeds; error rides inside
    events, _ = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["searching", "error", "done"], f"unexpected: {types}"
    assert "额度" in next(e for e in events if e["type"] == "error")["message"]
