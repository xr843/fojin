"""``truncated`` 帧：答案被 max_tokens 截断时，流里要有一帧告诉前端「没写完」。

为什么：普通问答 ``max_tokens=2000``，贴一段长文求白话翻译会被截断（生产样本里有
「你还没翻译完呢」）。此前上游的 finish_reason 既不解析也不记日志——截断率量不出来，
前端也给不出「继续写完」。这里锁定三件事：帧的有无、帧的位置、日志里有 finish_reason。
"""
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_chat_stream_retrieved_event import (
    _events,
    _FakeSessionmaker,
    _make_prepare_chat_return,
    _sources,
)


def _mock_client_from_lines(lines: list[str]):
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


def _openai_lines(tokens: list[str], finish_reason: str) -> list[str]:
    """OpenAI 兼容格式：正文块之后是一个 delta 为空、只带 finish_reason 的收尾块
    （DeepSeek/OpenAI 实际就是这么发的），最后 [DONE]。"""
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}" for t in tokens]
    lines.append(f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': finish_reason}]})}")
    lines.append("data: [DONE]")
    return lines


def _anthropic_lines(tokens: list[str], stop_reason: str) -> list[str]:
    lines = [
        f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': t}})}"
        for t in tokens
    ]
    lines.append(f"data: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason}})}")
    lines.append("data: " + json.dumps({"type": "message_stop"}))
    return lines


async def _run(lines: list[str], *, provider: str = "openai") -> list[dict]:
    prep = list(_make_prepare_chat_return(_sources()))
    if provider == "anthropic":
        prep[1], prep[5] = "https://api.anthropic.com/v1", "anthropic"
    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=tuple(prep)), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", _mock_client_from_lines(lines)):
        from app.services.chat import send_message_stream

        chunks: list[str] = []
        async for chunk in send_message_stream(
            user_id=1, message="测试", sessionmaker=_FakeSessionmaker(),
        ):
            chunks.append(chunk)
    return _events(chunks)


TOKENS = ["色不异空", "，空不异色"]


@pytest.mark.anyio
async def test_length_finish_emits_truncated_frame_after_tokens_before_done():
    events = await _run(_openai_lines(TOKENS, "length"))
    types = [e.get("type") for e in events]

    assert "truncated" in types, f"finish_reason=length 却没有 truncated 帧；实际: {types}"
    frame = next(e for e in events if e.get("type") == "truncated")
    assert frame.get("reason") == "length", frame
    last_token = max(i for i, t in enumerate(types) if t == "token")
    assert last_token < types.index("truncated") < types.index("done"), (
        f"truncated 必须在最后一个 token 之后、done 之前；实际顺序: {types}"
    )
    # 收尾块 delta 为空，不能把它当成一个空 token 或把正文弄丢
    assert "".join(e["content"] for e in events if e.get("type") == "token") == "".join(TOKENS)


@pytest.mark.anyio
async def test_stop_finish_emits_no_truncated_frame():
    events = await _run(_openai_lines(TOKENS, "stop"))
    types = [e.get("type") for e in events]
    assert "truncated" not in types, f"正常结束不该有 truncated 帧；实际: {types}"
    assert "done" in types


@pytest.mark.anyio
async def test_anthropic_max_tokens_stop_reason_emits_truncated_frame():
    events = await _run(_anthropic_lines(TOKENS, "max_tokens"), provider="anthropic")
    frame = next((e for e in events if e.get("type") == "truncated"), None)
    assert frame is not None, (
        f"Anthropic stop_reason=max_tokens 应发 truncated；实际: {[e.get('type') for e in events]}"
    )
    assert frame.get("reason") == "max_tokens"


@pytest.mark.anyio
async def test_finish_reason_is_logged_for_every_completed_answer(caplog):
    """截断率的分母与分子都从这行日志来：每条完成的回答都要写 finish_reason。"""
    caplog.set_level(logging.INFO, logger="app.services.chat")
    await _run(_openai_lines(TOKENS, "length"))
    done_lines = [r.getMessage() for r in caplog.records if "phase-2 LLM done" in r.getMessage()]
    assert done_lines, "缺少 phase-2 LLM done 日志"
    assert "finish_reason=length" in done_lines[-1], done_lines[-1]

    caplog.clear()
    await _run(_openai_lines(TOKENS, "stop"))
    done_lines = [r.getMessage() for r in caplog.records if "phase-2 LLM done" in r.getMessage()]
    assert "finish_reason=stop" in done_lines[-1], done_lines[-1]
