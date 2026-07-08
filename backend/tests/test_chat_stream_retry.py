"""Tests for the same-provider transient retry in send_message_stream.

``_stream_attempt`` wraps each provider's stream with ONE retry, fired only
when the failure is transient (network / timeout / 5xx / 429) AND no token has
been yielded yet. This is the only resilience a BYOK request gets (it has no
cross-provider fallback). The invariants under test:

  * a transient pre-token failure retries the SAME provider once and succeeds;
  * a failure AFTER the first token is NOT retried (would duplicate output);
  * a non-transient 4xx is NOT retried (it would just fail again).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.schemas.chat import ChatSource


def _make_prepare_chat_return(sources: list[ChatSource], *, is_byok: bool):
    fake_session = MagicMock()
    fake_session.id = 42
    llm_messages = [{"role": "user", "content": "测试"}]
    return (
        fake_session, "https://api.example.com/v1", "fake-key", "test-model",
        is_byok, "openai", sources, llm_messages, [],
    )


def _fake_sources() -> list[ChatSource]:
    return [ChatSource(text_id=1, juan_num=1, chunk_text="色不异空", score=0.9, title_zh="心经")]


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    resp = httpx.Response(status, request=req)
    return httpx.HTTPStatusError(f"{status}", request=req, response=resp)


def _scripted_httpx(script: list, call_log: list):
    """Patched httpx.AsyncClient whose every ``client.stream(...)`` consumes the
    next behavior from ``script`` (shared across attempts):

      * list[str]                 -> yields those content deltas + [DONE]
      * Exception                 -> raised before any yield (pre-token failure)
      * (list[str], Exception)    -> yields the tokens, THEN raises (mid-stream)

    Each ``stream()`` call appends to ``call_log`` so tests can count attempts.
    """
    def _norm(b):
        if isinstance(b, tuple):
            return b
        if isinstance(b, Exception):
            return [], b
        return b, None

    def _make_resp(behavior):
        tokens, exc = _norm(behavior)
        mock_resp = MagicMock()

        async def aiter_lines():
            for t in tokens:
                yield f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}"
            if exc is not None:
                raise exc
            yield "data: [DONE]"

        mock_resp.aiter_lines = aiter_lines
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    class _StreamCM:
        def __init__(self, behavior):
            self._behavior = behavior

        async def __aenter__(self):
            return _make_resp(self._behavior)

        async def __aexit__(self, *_):
            return False

    class _ClientInstance:
        def stream(self, *args, **kwargs):
            behavior = script.pop(0)
            call_log.append(1)
            return _StreamCM(behavior)

    class _ClientCM:
        async def __aenter__(self):
            return _ClientInstance()

        async def __aexit__(self, *_):
            return False

    return MagicMock(return_value=_ClientCM())


class _FakeSessionmaker:
    def __call__(self):
        class _SessCM:
            async def __aenter__(self_inner):
                return AsyncMock()

            async def __aexit__(self_inner, *_):
                return False

        return _SessCM()


def _events(chunks: list[str]) -> list[dict]:
    out: list[dict] = []
    for c in chunks:
        c = c.strip()
        if not c.startswith("data: "):
            continue
        try:
            out.append(json.loads(c[len("data: "):]))
        except json.JSONDecodeError:
            pass
    return out


async def _run(script: list, *, is_byok: bool):
    call_log: list = []
    prepare_return = _make_prepare_chat_return(_fake_sources(), is_byok=is_byok)
    mock_client_cls = _scripted_httpx(script, call_log)
    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.chat.asyncio.sleep", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):
        from app.services.chat import send_message_stream

        chunks: list[str] = []
        async for chunk in send_message_stream(user_id=1, message="测试", sessionmaker=_FakeSessionmaker()):
            chunks.append(chunk)
    return _events(chunks), call_log


@pytest.mark.anyio
async def test_transient_pretoken_failure_retries_same_provider():
    """A ConnectError before any token → one same-provider retry that succeeds.
    BYOK (no fallback), so 2 stream() calls prove it was a retry, not a fallback."""
    script = [httpx.ConnectError("boom"), ["般", "若"]]
    events, call_log = await _run(script, is_byok=True)

    assert len(call_log) == 2, f"expected exactly one retry (2 stream calls); got {len(call_log)}"
    tokens = [e["content"] for e in events if e.get("type") == "token"]
    assert tokens == ["般", "若"], tokens
    assert not [e for e in events if e.get("type") == "error"], "retry succeeded; no error expected"


@pytest.mark.anyio
async def test_no_retry_after_first_token():
    """A failure AFTER a token has streamed must NOT retry (would duplicate)."""
    script = [(["般"], httpx.ReadError("mid-stream"))]
    events, call_log = await _run(script, is_byok=True)

    assert len(call_log) == 1, f"must not retry after a token; got {len(call_log)} stream calls"
    tokens = [e["content"] for e in events if e.get("type") == "token"]
    assert tokens == ["般"], tokens
    assert any(e.get("type") == "error" for e in events), "mid-stream break should surface an error"


@pytest.mark.anyio
async def test_non_transient_4xx_is_not_retried():
    """A 401 (bad key) is permanent — surface immediately, no retry."""
    script = [_http_status_error(401)]
    events, call_log = await _run(script, is_byok=True)

    assert len(call_log) == 1, f"4xx must not be retried; got {len(call_log)} stream calls"
    assert any(e.get("type") == "error" for e in events), "the 401 must surface as an error event"


@pytest.mark.anyio
async def test_transient_5xx_is_retried():
    """A 503 before any token is transient → one retry that then succeeds."""
    script = [_http_status_error(503), ["四", "圣", "谛"]]
    events, call_log = await _run(script, is_byok=True)

    assert len(call_log) == 2, f"5xx should be retried once; got {len(call_log)} stream calls"
    tokens = [e["content"] for e in events if e.get("type") == "token"]
    assert tokens == ["四", "圣", "谛"], tokens
