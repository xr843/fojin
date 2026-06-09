"""Heartbeat watchdog for ``/chat/stream`` SSE.

Locks the contract that ``_interleave_heartbeat`` emits ``("ping", None)``
markers whenever the wrapped inner generator goes quiet for longer than
``heartbeat_interval``. The outer ``send_message_stream`` translates these
into ``: keepalive\\n\\n`` SSE comment frames so Cloudflare's free-plan
edge (~100s) and nginx ``proxy_read_timeout`` (120s) don't sever the
connection while DeepSeek V4 Pro pauses generation near the end of a
long reader-mode answer. See ``feedback_log_before_second_guess`` and
the 2026-06-09 T1579 juan-7 incident write-up.
"""

import asyncio

import pytest

from app.services.chat import _interleave_heartbeat


async def _fast_gen():
    for chunk in ["a", "b", "c"]:
        yield chunk


async def _slow_first_token(delay: float):
    await asyncio.sleep(delay)
    yield "late"


async def _raises_after_n(n: int):
    for i in range(n):
        yield f"chunk-{i}"
    raise RuntimeError("boom")


@pytest.mark.anyio
async def test_no_ping_when_inner_fast():
    """A generator that yields immediately should produce zero ping markers —
    the wrapper must not introduce phantom traffic on the happy path.
    """
    events: list[tuple[str, object]] = []
    async for kind, payload in _interleave_heartbeat(_fast_gen(), heartbeat_interval=1.0):
        events.append((kind, payload))

    assert events == [("content", "a"), ("content", "b"), ("content", "c")]


@pytest.mark.anyio
async def test_ping_emitted_when_inner_idle_longer_than_interval():
    """When the inner generator stalls past ``heartbeat_interval``, the
    wrapper must emit at least one ``ping`` before the late token, then
    pass the token through unchanged.
    """
    events: list[tuple[str, object]] = []
    async for kind, payload in _interleave_heartbeat(
        _slow_first_token(delay=0.3), heartbeat_interval=0.1
    ):
        events.append((kind, payload))

    pings = [e for e in events if e[0] == "ping"]
    contents = [e for e in events if e[0] == "content"]
    assert pings, "expected at least one ping before slow first token, got none"
    assert contents == [("content", "late")]
    # All pings must come before the content (consumer expects pings during
    # the idle gap, not interleaved after content has arrived).
    assert events.index(("ping", None)) < events.index(("content", "late"))


@pytest.mark.anyio
async def test_exception_from_inner_propagates_after_buffered_content():
    """An exception raised by the inner generator must surface on the
    consumer side ONLY after every already-yielded ``content`` chunk is
    delivered — the producer side puts items into a queue, so a naive
    implementation could swallow buffered content if the error skipped
    ahead. We yield several items before raising to lock the FIFO contract
    that ``send_message_stream``'s post-first-token error path depends on
    (it records ``full_answer`` from every delivered chunk and only then
    emits the "回答中途中断" SSE error event).
    """
    events: list[tuple[str, object]] = []
    with pytest.raises(RuntimeError, match="boom"):
        async for kind, payload in _interleave_heartbeat(
            _raises_after_n(8), heartbeat_interval=1.0
        ):
            events.append((kind, payload))

    assert events == [("content", f"chunk-{i}") for i in range(8)]


@pytest.mark.anyio
async def test_consumer_cancellation_cleans_up_producer():
    """When the consumer side is cancelled (e.g. client disconnects mid-
    stream), the internal producer task must be cancelled too — otherwise
    we leak a background task holding an open httpx connection.
    """

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _hang_after_start():
        started.set()
        try:
            await asyncio.sleep(10)
            yield "unreachable"
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def _consume():
        async for _ in _interleave_heartbeat(_hang_after_start(), heartbeat_interval=5.0):
            pass

    task = asyncio.create_task(_consume())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The cancellation chain (consumer → wrapper.finally → producer.cancel →
    # inner gen.except CancelledError → cancelled.set()) crosses several
    # event-loop ticks. Wait up to 1s rather than asserting on a single
    # ``sleep(0)`` so the test doesn't flake under shared-runner load.
    await asyncio.wait_for(cancelled.wait(), timeout=1.0)
    assert cancelled.is_set(), "inner producer was not cancelled when consumer aborted"
