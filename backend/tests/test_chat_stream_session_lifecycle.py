"""Regression test for the /chat/stream DB-session-handoff contract.

Locks the invariant that ``send_message_stream`` releases its prep-phase
session BEFORE entering the LLM-streaming phase, and opens a fresh session
ONLY when persisting the final message. The legacy shape (single
``Depends(get_db)`` session pinned across the whole generator) exhausted
the PG pool under modest concurrency — see project_fojin_db_pool_streaming
and PR #649.
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
    """Same mock pattern as test_chat_sources_order — supports
    ``async with httpx.AsyncClient() as client: async with client.stream(...) as resp``.
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


class _CountingSessionmaker:
    """Drop-in for ``async_session`` that records when sessions open/close
    relative to LLM-stream activity.

    Each ``async with sessionmaker() as db`` produces a fresh AsyncMock and
    appends to ``opens`` / ``closes``. The phase ordering invariant the
    refactor must hold is: every ``close`` happens before the first LLM
    yield, OR after the last LLM yield — never spanning the LLM phase.
    """

    def __init__(self):
        self.opens: list[int] = []   # sequence-of-events index
        self.closes: list[int] = []
        self.event_log: list[str] = []  # interleaved events for readable assert messages
        self._t = 0
        self._tick_lock = False

    def _tick(self, kind: str) -> int:
        self._t += 1
        self.event_log.append(f"{self._t}:{kind}")
        return self._t

    def __call__(self):
        outer = self

        class _SessCM:
            async def __aenter__(self_inner):
                outer.opens.append(outer._tick("OPEN"))
                return AsyncMock()  # the db handle — every method awaited returns AsyncMock

            async def __aexit__(self_inner, *_):
                outer.closes.append(outer._tick("CLOSE"))
                return False

        return _SessCM()


@pytest.mark.anyio
async def test_session_released_before_llm_stream_starts():
    """Phase 1 session must close BEFORE the first LLM token is yielded.

    The whole point of the refactor: pool slot returned by the time we
    start waiting on the LLM. If a future change re-introduces the legacy
    shape (DI session pinned across the stream), this assertion fails
    because the close event would land after the first token event.
    """
    sources = _make_fake_sources()
    prepare_return = _make_prepare_chat_return(sources)
    counting = _CountingSessionmaker()

    # Mock the LLM stream so we can observe when token-yielding begins —
    # the assertion is that session 1 closed before any token arrived.
    token_yield_ticks: list[int] = []

    def _mock_httpx_factory(tokens):
        lines = [f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}" for t in tokens]
        lines.append("data: [DONE]")
        mock_resp = MagicMock()

        async def aiter_lines():
            for line in lines:
                token_yield_ticks.append(counting._tick("LLM_YIELD"))
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

    mock_client_cls = _mock_httpx_factory(["般", "若"])

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):
        from app.services.chat import send_message_stream

        chunks = []
        async for chunk in send_message_stream(
            user_id=1, message="测试", sessionmaker=counting,
        ):
            chunks.append(chunk)

    # Sanity: exactly two sessions opened (prep, save) and both closed.
    assert len(counting.opens) == 2, (
        f"expected 2 sessions (prep + save), got {len(counting.opens)} "
        f"events={counting.event_log}"
    )
    assert len(counting.closes) == 2, (
        f"expected 2 closes, got {len(counting.closes)} events={counting.event_log}"
    )

    # The critical invariant: first CLOSE precedes first LLM_YIELD.
    first_close = counting.closes[0]
    first_llm_yield = token_yield_ticks[0]
    assert first_close < first_llm_yield, (
        f"DB session must close before LLM stream begins.\n"
        f"first CLOSE at tick {first_close}, first LLM_YIELD at tick {first_llm_yield}.\n"
        f"event log: {counting.event_log}"
    )

    # And the second OPEN happens AFTER the last LLM yield (save phase).
    second_open = counting.opens[1]
    last_llm_yield = token_yield_ticks[-1]
    assert second_open > last_llm_yield, (
        f"save-phase session must open after LLM stream ends.\n"
        f"second OPEN at tick {second_open}, last LLM_YIELD at tick {last_llm_yield}.\n"
        f"event log: {counting.event_log}"
    )


@pytest.mark.anyio
async def test_prep_phase_error_still_closes_session():
    """A ValidationError raised inside _prepare_chat must not leak the
    session — the ``async with`` block's __aexit__ runs in either case,
    and the error event is yielded only after the session is back in
    the pool.
    """
    from app.core.exceptions import QuotaExceededError

    counting = _CountingSessionmaker()

    with patch(
        "app.services.chat._prepare_chat",
        new_callable=AsyncMock,
        side_effect=QuotaExceededError(limit=30),
    ):
        from app.services.chat import send_message_stream

        chunks = []
        async for chunk in send_message_stream(
            user_id=1, message="测试", sessionmaker=counting,
        ):
            chunks.append(chunk)

    # One session opened for prep, no save phase (prep failed).
    assert len(counting.opens) == 1
    assert len(counting.closes) == 1
    # And it closed before the error event reached the wire.
    # We can't observe network writes directly here, but we *can* confirm
    # the close completed before the generator finished producing chunks.
    assert any("error" in c for c in chunks), "error event must be yielded"
    assert counting.closes[0] > 0  # close did happen


def test_chat_stream_endpoint_does_not_depend_on_get_db():
    """Endpoint must not take a `db` parameter. If a future change adds
    ``Depends(get_db)`` back to ``chat_stream``, FastAPI's DI would once
    again pin a PG connection for the entire 60-120s SSE-stream lifetime
    — the exact production-incident shape this refactor exists to
    eliminate (see project_fojin_db_pool_streaming). Signature snapshot
    so the regression bricks CI before it bricks the pool."""
    import inspect

    from app.api.chat import chat_stream

    sig = inspect.signature(chat_stream)
    assert "db" not in sig.parameters, (
        "chat_stream must NOT depend on get_db — that's the legacy shape "
        "that exhausted the PG pool. Generator owns its sessions via the "
        "module-level async_session factory instead. "
        f"got params={list(sig.parameters)}"
    )


@pytest.mark.anyio
async def test_quota_increment_uses_explicit_update():
    """Quota must increment via explicit UPDATE statement, not by mutating
    the User attribute. ``user`` is loaded by ``get_optional_user`` on a
    different session from the chat-stream prep session; attribute
    mutation against a foreign session silently no-ops on flush() and the
    quota never persists. Regression for code-review C1."""
    import datetime as _dt
    from unittest.mock import AsyncMock, MagicMock

    from app.services.chat import _check_daily_quota

    user = MagicMock()
    user.id = 7
    user.daily_chat_count = 5
    user.last_chat_date = _dt.date.today()

    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()

    await _check_daily_quota(db, user)

    # The mitigation: an UPDATE was emitted, not a flush of attribute deltas.
    assert db.execute.await_count == 1, (
        "_check_daily_quota must issue an explicit UPDATE so the increment "
        "persists regardless of which session loaded `user`."
    )
    # And the in-memory user was patched to match — caller's later reads
    # in the same request stay coherent.
    assert user.daily_chat_count == 6


@pytest.mark.anyio
async def test_attachments_consumed_uses_explicit_update():
    """``_mark_attachments_consumed`` must persist via UPDATE statement,
    not by setting ``row.consumed_at = now`` on rows loaded by a different
    session. Same root cause as quota regression — detached rows ignored
    by ``flush()``. Regression for code-review C2 (which has security
    implications: ``consumed_at IS NULL`` is the anti-enumeration
    mitigation for anonymous uploads, schemas/chat.py)."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.chat import _mark_attachments_consumed

    row1 = MagicMock()
    row1.id = 11
    row1.consumed_at = None
    row2 = MagicMock()
    row2.id = 22
    row2.consumed_at = None

    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    await _mark_attachments_consumed(db, [row1, row2])

    assert db.execute.await_count == 1, (
        "_mark_attachments_consumed must issue an explicit UPDATE so "
        "consumed_at persists for rows loaded by a foreign session."
    )
    assert db.commit.await_count == 1


@pytest.mark.anyio
async def test_save_phase_failure_still_yields_done():
    """A failure inside the save-phase ``async with`` must not escape the
    generator — the frontend SSE consumer needs the ``done`` event to
    finalize its UI state, otherwise it sits in "thinking…" forever.
    Regression for code-review I3."""
    sources = _make_fake_sources()
    prepare_return = _make_prepare_chat_return(sources)
    counting = _CountingSessionmaker()
    mock_client_cls = _make_mock_httpx_client(["a", "b"])

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, side_effect=RuntimeError("simulated PG flake")), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):
        from app.services.chat import send_message_stream

        chunks = []
        async for chunk in send_message_stream(
            user_id=1, message="测试 save fail", sessionmaker=counting,
        ):
            chunks.append(chunk)

    # The done event must reach the wire even though save raised.
    assert any('"type": "done"' in c for c in chunks), (
        "save-phase failure swallowed the done event — frontend would "
        f"hang in 'thinking…' state. chunks={chunks!r}"
    )


@pytest.mark.anyio
async def test_anonymous_user_skips_save_phase():
    """Anonymous users (chat_session is None) only need the prep session;
    no save session should be opened. The legacy shape held one session
    for the whole stream regardless — the refactor cleanly avoids the
    save-phase open when there's nothing to save.
    """
    sources = _make_fake_sources()
    # Anonymous: chat_session is None per _prepare_chat contract
    prepare_return = (
        None, "https://api.example.com/v1", "fake-key", "test-model",
        False, "openai", sources,
        [{"role": "user", "content": "anon"}], [],
    )
    counting = _CountingSessionmaker()
    mock_client_cls = _make_mock_httpx_client(["anon-reply"])

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):
        from app.services.chat import send_message_stream

        chunks = []
        async for chunk in send_message_stream(
            user_id=None, message="anon question", sessionmaker=counting,
        ):
            chunks.append(chunk)

    assert len(counting.opens) == 1, (
        f"anonymous flow should open exactly one session (prep), got {len(counting.opens)}"
    )
    assert len(counting.closes) == 1
