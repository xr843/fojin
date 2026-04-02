"""测试 chat SSE 事件流中事件的顺序。

验证 send_message_stream 生成器输出的 SSE 事件满足前端预期的顺序：
  padding → searching → session_id → token(s) → sources → done
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.chat import ChatSource


def _parse_sse_events(raw_chunks: list[str]) -> list[dict]:
    """从 SSE 原始 chunk 中解析出 data 事件，忽略 padding 注释行。"""
    events = []
    for chunk in raw_chunks:
        chunk = chunk.strip()
        if not chunk or chunk.startswith(":"):
            # padding 或 SSE 注释行，跳过
            continue
        if chunk.startswith("data: "):
            payload = chunk[len("data: "):]
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


def _make_fake_sources() -> list[ChatSource]:
    """构造测试用的 ChatSource 列表。"""
    return [
        ChatSource(text_id=1, juan_num=1, chunk_text="色不异空", score=0.9, title_zh="心经"),
        ChatSource(text_id=2, juan_num=1, chunk_text="观自在菩萨", score=0.8, title_zh="般若经"),
    ]


def _make_prepare_chat_return(sources: list[ChatSource]):
    """构造 _prepare_chat 的返回值元组。"""
    fake_session = MagicMock()
    fake_session.id = 42
    llm_messages = [
        {"role": "system", "content": "你是佛津助手"},
        {"role": "user", "content": "什么是般若"},
    ]
    return (fake_session, "https://api.example.com/v1", "fake-key", "test-model", False, "openai", sources, llm_messages)


def _make_mock_httpx_client(tokens: list[str]):
    """构造模拟 httpx.AsyncClient，支持 async with client, client.stream(...) as resp 模式。

    tokens: LLM 逐个返回的 token 列表。
    返回一个可替换 httpx.AsyncClient 的 mock 类。
    """
    lines = []
    for token in tokens:
        chunk = {"choices": [{"delta": {"content": token}}]}
        lines.append(f"data: {json.dumps(chunk)}")
    lines.append("data: [DONE]")

    # 模拟 streaming response
    mock_resp = MagicMock()

    async def aiter_lines():
        for line in lines:
            yield line

    mock_resp.aiter_lines = aiter_lines
    mock_resp.raise_for_status = MagicMock()

    # client.stream() 返回的 async context manager
    # 注意：必须用 MagicMock 实现 __aenter__/__aexit__，而非 AsyncMock
    # 因为 AsyncMock.method() 返回 coroutine，不能直接用作 async with 目标
    class _StreamCM:
        async def __aenter__(self):
            return mock_resp
        async def __aexit__(self, *args):
            return False

    # client 本身需要一个同步的 stream() 方法返回 async cm
    class _ClientInstance:
        def stream(self, *args, **kwargs):
            return _StreamCM()

    # AsyncClient() 返回的 async context manager
    class _ClientCM:
        async def __aenter__(self):
            return _ClientInstance()
        async def __aexit__(self, *args):
            return False

    mock_cls = MagicMock(return_value=_ClientCM())
    return mock_cls


@pytest.mark.anyio
async def test_sources_after_tokens():
    """验证 sources 事件出现在最后一个 token 事件之后（先论点后论据）。

    预期事件顺序：searching → session_id → token → token → sources → done
    """
    sources = _make_fake_sources()
    prepare_return = _make_prepare_chat_return(sources)
    mock_client_cls = _make_mock_httpx_client(["般若", "是智慧"])

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):

        from app.services.chat import send_message_stream

        db = AsyncMock()
        chunks = []
        async for chunk in send_message_stream(db, user_id=1, message="什么是般若"):
            chunks.append(chunk)

    events = _parse_sse_events(chunks)
    event_types = [e["type"] for e in events]

    # 基本顺序验证
    assert event_types[0] == "searching", f"第一个事件应为 searching，实际为 {event_types[0]}"
    assert event_types[1] == "session_id", f"第二个事件应为 session_id，实际为 {event_types[1]}"
    assert event_types[-1] == "done", f"最后一个事件应为 done，实际为 {event_types[-1]}"

    # sources 必须在所有 token 之后
    sources_idx = event_types.index("sources")
    last_token_idx = len(event_types) - 1 - event_types[::-1].index("token")
    assert sources_idx > last_token_idx, (
        f"sources 事件（位置 {sources_idx}）应在最后一个 token 事件（位置 {last_token_idx}）之后"
    )

    # 验证 sources 事件内容
    sources_event = events[sources_idx]
    assert len(sources_event["sources"]) == 2
    assert sources_event["sources"][0]["title_zh"] == "心经"

    # 验证 searching 事件内容
    searching_event = events[0]
    assert "检索" in searching_event["message"]


@pytest.mark.anyio
async def test_empty_sources_not_emitted():
    """验证空 sources 时不发送 sources 事件。

    当 RAG 检索无结果时，事件流应直接从 session_id 跳到 token，
    不包含 sources 事件。
    """
    # 空 sources 列表
    prepare_return = _make_prepare_chat_return(sources=[])
    mock_client_cls = _make_mock_httpx_client(["佛", "法"])

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):

        from app.services.chat import send_message_stream

        db = AsyncMock()
        chunks = []
        async for chunk in send_message_stream(db, user_id=1, message="什么是佛法"):
            chunks.append(chunk)

    events = _parse_sse_events(chunks)
    event_types = [e["type"] for e in events]

    assert "sources" not in event_types, (
        f"空 sources 时不应发送 sources 事件，但事件流中包含: {event_types}"
    )
    # 验证基本结构仍然完整
    assert event_types[0] == "searching"
    assert event_types[1] == "session_id"
    assert event_types[-1] == "done"
    assert "token" in event_types


@pytest.mark.anyio
async def test_session_id_value_correct():
    """验证 session_id 事件携带正确的会话 ID 值。"""
    sources = _make_fake_sources()
    prepare_return = _make_prepare_chat_return(sources)
    mock_client_cls = _make_mock_httpx_client(["OK"])

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock, return_value=prepare_return), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", mock_client_cls):

        from app.services.chat import send_message_stream

        db = AsyncMock()
        chunks = []
        async for chunk in send_message_stream(db, user_id=1, message="测试"):
            chunks.append(chunk)

    events = _parse_sse_events(chunks)
    session_event = events[1]  # searching 之后是 session_id
    assert session_event["type"] == "session_id"
    assert session_event["session_id"] == 42, (
        f"session_id 应为 42，实际为 {session_event['session_id']}"
    )


@pytest.mark.anyio
async def test_error_during_prepare_yields_error_and_done():
    """验证 _prepare_chat 抛出异常时，事件流包含 error + done。

    当验证失败、配额耗尽等情况发生时，应返回 error 事件后立即 done，
    不应出现 session_id、sources 或 token 事件。
    """
    from app.core.exceptions import QuotaExceededError

    with patch(
        "app.services.chat._prepare_chat",
        new_callable=AsyncMock,
        side_effect=QuotaExceededError(limit=30),
    ):
        from app.services.chat import send_message_stream

        db = AsyncMock()
        chunks = []
        async for chunk in send_message_stream(db, user_id=1, message="测试配额"):
            chunks.append(chunk)

    events = _parse_sse_events(chunks)
    event_types = [e["type"] for e in events]

    assert event_types == ["searching", "error", "done"], (
        f"prepare 异常时应为 [searching, error, done]，实际为 {event_types}"
    )
    assert "session_id" not in event_types
    assert "sources" not in event_types
    assert "token" not in event_types
