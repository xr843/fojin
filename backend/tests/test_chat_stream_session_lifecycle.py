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


class _HandleCapturingSessionmaker:
    """Like _CountingSessionmaker but keeps each db handle so a test can
    assert what was called on the prep/save sessions."""

    def __init__(self):
        self.handles: list = []

    def __call__(self):
        outer = self

        class _CM:
            async def __aenter__(self_inner):
                h = AsyncMock()
                outer.handles.append(h)
                return h

            async def __aexit__(self_inner, *_):
                return False

        return _CM()


@pytest.mark.anyio
async def test_streaming_prep_commits_so_quota_persists():
    """The streaming prep session must COMMIT before it closes.

    _check_daily_quota issues UPDATE + flush() but no commit, and the prep
    block deliberately relies on close()->rollback to expire detached ORM
    instances — which ALSO discards the uncommitted quota UPDATE. So on the
    /chat/stream path the logged-in daily limit (FREE_DAILY_LIMIT_USER)
    silently never persists, leaving the free tier effectively unbounded and
    burning the platform key. Pin that the prep session commits. Regression
    for the streaming quota-leak audit finding (2026-06-23)."""
    sources = _make_fake_sources()
    prepare_return = _make_prepare_chat_return(sources)
    sm = _HandleCapturingSessionmaker()
    mock_client_cls = _make_mock_httpx_client(["般", "若"])

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):
        from app.services.chat import send_message_stream

        async for _ in send_message_stream(user_id=1, message="测试", sessionmaker=sm):
            pass

    assert sm.handles, "no session opened"
    prep_handle = sm.handles[0]
    assert prep_handle.commit.await_count >= 1, (
        "streaming prep session must commit so _check_daily_quota's UPDATE "
        "survives close()->rollback; otherwise logged-in daily quota is a "
        "no-op on /chat/stream"
    )


@pytest.mark.anyio
async def test_attachments_consumed_uses_explicit_update():
    """``_mark_attachments_consumed`` must persist via UPDATE statement on
    plain ids, not by mutating ORM rows. It takes ``pending_ids: list[int]``
    so the streaming caller can snapshot them while the rows are still bound
    (the prep session detaches+expires them on close — reading .id there
    would raise DetachedInstanceError and silently skip the stamp). Regression
    for code-review C2 (security: ``consumed_at IS NULL`` is the
    anti-enumeration mitigation for anonymous uploads, schemas/chat.py)."""
    from unittest.mock import AsyncMock

    from app.services.chat import _mark_attachments_consumed

    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    await _mark_attachments_consumed(db, [11, 22])

    assert db.execute.await_count == 1, (
        "_mark_attachments_consumed must issue an explicit UPDATE so "
        "consumed_at persists for the given ids."
    )
    assert db.commit.await_count == 1


@pytest.mark.anyio
async def test_empty_pending_ids_is_noop():
    """No attachments → no UPDATE, no commit (fast path)."""
    from unittest.mock import AsyncMock

    from app.services.chat import _mark_attachments_consumed

    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    await _mark_attachments_consumed(db, [])

    assert db.execute.await_count == 0
    assert db.commit.await_count == 0


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
    """Anonymous users (chat_session is None) must not open a message-save
    session — their conversation content is deliberately never persisted.

    Since the daily-count feature they DO open one extra short session to
    bump daily_metric_counts (count only, no content — see
    tests/test_daily_metrics.py). So the contract is now: prep + counter
    = exactly 2 opens, and never a third (message save).
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

    assert len(counting.opens) == 2, (
        "anonymous flow should open exactly two sessions (prep + daily "
        f"counter), got {len(counting.opens)}"
    )
    assert len(counting.closes) == 2


class _DetachOnCloseSessionmaker:
    """Sessionmaker that detaches a target row when its session closes —
    faithfully reproducing SQLAlchemy's behaviour. The real prep session
    leaves an open transaction (create_session's ``refresh()`` + quota
    ``flush()`` never commit), so ``close()`` rolls it back, and a rollback
    EXPIRES every loaded instance. Reading ``chat_session.id`` afterwards
    then raises ``DetachedInstanceError``.

    The first ``close`` (the prep session) flips ``row._detached`` so any
    later ``.id`` read raises — exactly the production failure mode that the
    legacy ``MagicMock`` fixture (``.id = 42``, never detaches) could not
    catch.
    """

    def __init__(self, row):
        self._row = row
        self.closes = 0

    def __call__(self):
        outer = self

        class _SessCM:
            async def __aenter__(self_inner):
                return AsyncMock()

            async def __aexit__(self_inner, *_):
                outer.closes += 1
                outer._row._detached = True
                return False

        return _SessCM()


class _DetachableSessionRow:
    """Stand-in for a ChatSession ORM row: ``.id`` is readable while the
    owning session is open, and raises ``DetachedInstanceError`` once the
    session closes — the SQLAlchemy contract after a rollback-on-close."""

    def __init__(self, real_id: int):
        self._real_id = real_id
        self._detached = False

    @property
    def id(self) -> int:
        if self._detached:
            from sqlalchemy.orm.exc import DetachedInstanceError

            raise DetachedInstanceError(
                "Instance <ChatSession> is not bound to a Session; "
                "attribute refresh operation cannot proceed"
            )
        return self._real_id


@pytest.mark.anyio
async def test_session_id_read_before_prep_session_closes():
    """``chat_session.id`` must be captured INSIDE the prep ``async with``
    block, while the ORM row is still bound. The prep session's
    rollback-on-close expires the row, so any ``.id`` read AFTER the block
    raises ``DetachedInstanceError`` — the SSE generator then dies before
    emitting any answer or ``done``, and the frontend hangs forever on
    "正在检索经文并生成回答".

    Regression for the production incident where new-conversation chats
    stuck in that state. The pre-fix code read ``chat_session.id`` at the
    ``session_id`` yield (and again in the save phase); this test detaches
    the row exactly when the prep session closes, so the buggy path raises
    and the fixed path (int captured in-block) yields ``session_id: 42``.
    """
    sources = _make_fake_sources()
    row = _DetachableSessionRow(42)
    prepare_return = (
        row, "https://api.example.com/v1", "fake-key", "test-model",
        False, "openai", sources, [{"role": "user", "content": "测试"}], [],
    )
    sessionmaker = _DetachOnCloseSessionmaker(row)
    mock_client_cls = _make_mock_httpx_client(["般", "若"])

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):
        from app.services.chat import send_message_stream

        chunks = []
        async for chunk in send_message_stream(
            user_id=1, message="测试", sessionmaker=sessionmaker,
        ):
            chunks.append(chunk)

    # The session_id event must carry the real id (42), captured before the
    # prep session closed. Pre-fix this read raised DetachedInstanceError and
    # the generator never reached this event.
    sid_events = [c for c in chunks if '"type": "session_id"' in c]
    assert sid_events, f"no session_id event emitted; chunks={chunks!r}"
    assert '"session_id": 42' in sid_events[0], (
        f"session_id must be the captured int 42, got {sid_events[0]!r}"
    )
    # And the stream finished cleanly — the user gets a terminal event so the
    # UI leaves the "正在检索…" state.
    assert any('"type": "done"' in c for c in chunks), (
        f"done event missing — frontend would hang. chunks={chunks!r}"
    )


class _DetachableAttachmentRow:
    """ChatAttachment stand-in: ``.id`` / ``.consumed_at`` readable while the
    prep session is bound, raising once it closes — the same rollback-on-close
    contract as the chat_session row."""

    def __init__(self, real_id: int):
        self._real_id = real_id
        self._detached = False

    def _check(self):
        if self._detached:
            from sqlalchemy.orm.exc import DetachedInstanceError

            raise DetachedInstanceError(
                "Instance <ChatAttachment> is not bound to a Session"
            )

    @property
    def id(self) -> int:
        self._check()
        return self._real_id

    @property
    def consumed_at(self):
        self._check()
        return None


@pytest.mark.anyio
async def test_attachment_ids_captured_before_prep_session_closes():
    """The streaming save phase must call ``_mark_attachments_consumed`` with
    plain ids snapshotted INSIDE the prep block — never the detached ORM
    rows. After the prep session closes (rollback-on-close), reading
    ``row.id`` / ``row.consumed_at`` raises DetachedInstanceError, which
    ``_mark_attachments_consumed``'s try/except would swallow — silently
    skipping the ``consumed_at`` stamp and defeating the single-use
    anti-enumeration guard for anonymous uploads.

    Locks the contract: the save call receives ``[7]`` (the captured int),
    not the row object. A revert to passing rows fails this assertion.
    """
    sources = _make_fake_sources()
    chat_row = _DetachableSessionRow(1)
    attach_row = _DetachableAttachmentRow(7)
    prepare_return = (
        chat_row, "https://api.example.com/v1", "fake-key", "test-model",
        False, "openai", sources, [{"role": "user", "content": "测试"}],
        [attach_row],
    )

    mock_client_cls = _make_mock_httpx_client(["般", "若"])
    mark_spy = AsyncMock()

    # The prep close must detach BOTH rows (they belong to the same session).
    class _BothDetachSessionmaker:
        def __call__(self_inner):
            class _SessCM:
                async def __aenter__(self_cm):
                    return AsyncMock()

                async def __aexit__(self_cm, *_):
                    chat_row._detached = True
                    attach_row._detached = True
                    return False

            return _SessCM()

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", mark_spy), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):
        from app.services.chat import send_message_stream

        chunks = []
        async for chunk in send_message_stream(
            user_id=1, message="测试", sessionmaker=_BothDetachSessionmaker(),
        ):
            chunks.append(chunk)

    assert mark_spy.await_count == 1, (
        f"_mark_attachments_consumed must be called once; chunks={chunks!r}"
    )
    passed_ids = mark_spy.await_args.args[1]
    assert passed_ids == [7], (
        "save phase must pass plain ids captured before the prep session "
        f"closed, not detached rows. got {passed_ids!r}"
    )
    assert any('"type": "done"' in c for c in chunks)
