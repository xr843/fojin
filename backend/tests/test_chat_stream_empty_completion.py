"""Regression test for the empty-completion silent-hang bug.

When the LLM stream completes without ever yielding an answer token (and
without raising — an "empty but successful" completion), ``send_message_stream``
used to fall through to a bare ``done`` event. The frontend, which only leaves
its "正在检索经文并生成回答…" placeholder on a ``token`` or ``error`` event, then
hung on that fake-loading state forever — no answer, no error, no retry. This
was reproducible against production.

The guard emits an ``error`` event (so the client shows its retry affordance)
before ``done`` whenever the stream produced neither a token nor an error.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatSource


def _make_fake_sources() -> list[ChatSource]:
    return [
        ChatSource(text_id=1, juan_num=1, chunk_text="色不异空", score=0.9, title_zh="心经"),
    ]


def _make_prepare_chat_return(sources: list[ChatSource]):
    fake_session = MagicMock()
    fake_session.id = 42
    llm_messages = [{"role": "user", "content": "测试"}]
    return (
        fake_session, "https://api.example.com/v1", "fake-key", "test-model",
        False, "openai", sources, llm_messages, [],
    )


def _make_mock_httpx_client(tokens: list[str]):
    """Mock httpx.AsyncClient whose stream yields ``tokens`` then ``[DONE]``.

    Passing an empty list reproduces an "empty but successful" completion:
    the SSE stream carries only the terminal ``data: [DONE]`` and no content
    deltas, so ``_stream_llm_once`` yields nothing and never raises.
    """
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}" for t in tokens]
    lines.append("data: [DONE]")
    mock_resp = MagicMock()

    async def aiter_lines():
        for line in lines:
            yield line

    mock_resp.aiter_lines = aiter_lines
    mock_resp.raise_for_status = MagicMock()

    class _StreamCM:
        async def __aenter__(self): return mock_resp
        async def __aexit__(self, *_): return False

    class _ClientInstance:
        def stream(self, *args, **kwargs): return _StreamCM()

    class _ClientCM:
        async def __aenter__(self): return _ClientInstance()
        async def __aexit__(self, *_): return False

    return MagicMock(return_value=_ClientCM())


class _FakeSessionmaker:
    """Minimal ``async with sessionmaker() as db`` producing an AsyncMock db."""

    def __call__(self):
        class _SessCM:
            async def __aenter__(self_inner): return AsyncMock()
            async def __aexit__(self_inner, *_): return False

        return _SessCM()


def _events(chunks: list[str]) -> list[dict]:
    """Parse SSE ``data: {json}`` frames, skipping ``: keepalive`` comments."""
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


async def _run_stream(tokens: list[str]) -> list[dict]:
    prepare_return = _make_prepare_chat_return(_make_fake_sources())
    mock_client_cls = _make_mock_httpx_client(tokens)
    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):
        from app.services.chat import send_message_stream

        chunks: list[str] = []
        async for chunk in send_message_stream(
            user_id=1, message="测试", sessionmaker=_FakeSessionmaker(),
        ):
            chunks.append(chunk)
    return _events(chunks)


@pytest.mark.anyio
async def test_empty_completion_emits_error_not_bare_done():
    """An empty (token-less, error-less) stream must surface an ``error``
    event so the client can recover — never a silent bare ``done``."""
    events = await _run_stream(tokens=[])

    types = [e.get("type") for e in events]
    assert "token" not in types, f"empty completion must yield no token; got {types}"
    assert "error" in types, (
        f"empty completion must emit an 'error' event (not a silent done); got {types}"
    )
    # The error must precede done (client leaves the placeholder on 'error').
    assert types.index("error") < types.index("done"), (
        f"'error' must be emitted before 'done'; got {types}"
    )
    err = next(e for e in events if e.get("type") == "error")
    assert "回答" in err["message"] or "重试" in err["message"], err
    # code 是给埋点用的稳定标识，前端原样送进 Umami 的 chat_stream_error.reason。
    # 断流率的分子必须分得开成因：空回复要改的是模型/预算，上游超时要改的是运维，
    # 配额用完根本不是故障 —— 只看 message 分不开，因为它是一句会被润色的中文。
    assert err.get("code") == "empty_completion", (
        f"空回复必须带 code=empty_completion，实际 {err.get('code')!r}"
    )


@pytest.mark.anyio
async def test_normal_completion_is_unaffected():
    """Guard regression: a stream that does yield tokens still completes
    normally with token events and no spurious empty-completion error."""
    events = await _run_stream(tokens=["般", "若"])

    types = [e.get("type") for e in events]
    assert types.count("token") == 2, f"expected 2 token events; got {types}"
    assert "done" in types
    # No empty-completion error should be injected on the happy path.
    empty_errors = [
        e for e in events
        if e.get("type") == "error" and "未能生成任何回答内容" in e.get("message", "")
    ]
    assert not empty_errors, f"no empty-completion error expected on happy path; got {empty_errors}"
