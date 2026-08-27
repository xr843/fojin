"""「重新生成」：同一问题再答一次，替换本会话最后一轮问答。

为什么：30 天里约 88 次「隔一会儿把同一个问题原样再发一遍」没有任何失败或重试
在前面——用户是对答案不满意，而界面上没有「重新生成」。做成替换而不是追加：
上下文里不能带着上一个（不满意的）答案，否则模型多半照抄；历史里也不该留两份。

契约：
- ``ChatRequest.regenerate`` 默认 False；
- 拼 LLM 上下文时去掉最后一轮（最后一条 assistant + 它之前最近的一条 user），按 id
  而不是 created_at 判先后（同一次提交写入的两行时间戳可能相同）；
- 只有新答案成功落库时才删旧的那对；失败答案（_is_failed_answer）不删、也不存。
"""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.chat import ChatRequest
from tests.test_chat_stream_retrieved_event import (
    _FakeSessionmaker,
    _make_prepare_chat_return,
    _sources,
)
from tests.test_chat_stream_truncated_event import _mock_client_from_lines, _openai_lines


def test_chat_request_regenerate_defaults_false():
    assert ChatRequest(message="x").regenerate is False
    assert ChatRequest(message="x", regenerate=True).regenerate is True


HIST = [
    NS(id=1, role="user"), NS(id=2, role="assistant"),
    NS(id=3, role="user"), NS(id=4, role="assistant"),
]


def test_last_exchange_ids_picks_last_assistant_and_its_user_by_id():
    from app.services.chat import _last_exchange_ids

    assert _last_exchange_ids(HIST) == {3, 4}
    # created_at 顺序乱了也按 id 判
    assert _last_exchange_ids([HIST[1], HIST[0], HIST[3], HIST[2]]) == {3, 4}
    assert _last_exchange_ids([]) == set()
    # 还没有任何回答：没有可替换的一轮
    assert _last_exchange_ids([NS(id=1, role="user")]) == set()


def test_history_for_context_drops_last_exchange_only_when_regenerating():
    from app.services.chat import _history_for_context

    assert [m.id for m in _history_for_context(HIST, regenerate=True)] == [1, 2]
    assert [m.id for m in _history_for_context(HIST, regenerate=False)] == [1, 2, 3, 4]


async def _run(*, regenerate: bool, failed: bool = False) -> AsyncMock:
    lines = _openai_lines(["般", "若"], "stop")
    delete_mock = AsyncMock()
    patches = [
        patch("app.services.chat._prepare_chat", new_callable=AsyncMock,
              return_value=_make_prepare_chat_return(_sources())),
        patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99),
        patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock),
        patch("app.services.chat.httpx.AsyncClient", _mock_client_from_lines(lines)),
        patch("app.services.chat._delete_last_exchange", delete_mock),
    ]
    if failed:
        patches.append(patch("app.services.chat._is_failed_answer", return_value=True))
    for p in patches:
        p.start()
    try:
        from app.services.chat import send_message_stream

        async for _ in send_message_stream(
            user_id=1, message="测试", regenerate=regenerate, sessionmaker=_FakeSessionmaker(),
        ):
            pass
    finally:
        for p in reversed(patches):
            p.stop()
    return delete_mock


@pytest.mark.anyio
async def test_regenerate_deletes_last_exchange_in_the_save_session():
    delete_mock = await _run(regenerate=True)
    delete_mock.assert_awaited_once()
    assert delete_mock.await_args.args[1] == 42, delete_mock.await_args


@pytest.mark.anyio
async def test_plain_send_never_deletes():
    delete_mock = await _run(regenerate=False)
    delete_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_regenerate_keeps_old_answer_when_new_one_failed():
    """新答案失败不落库，旧的那对也必须留着——否则用户点一下「重新生成」反而把原答案弄丢。"""
    delete_mock = await _run(regenerate=True, failed=True)
    delete_mock.assert_not_awaited()


async def test_stream_endpoint_passes_regenerate_to_service(client):
    seen: dict = {}

    async def fake_stream(*args, **kwargs):
        seen.update(kwargs)
        yield 'data: {"type": "done"}\n\n'

    with patch("app.api.chat.send_message_stream", new=fake_stream):
        resp = await client.post("/api/chat/stream", json={"message": "x", "regenerate": True})
    assert resp.status_code == 200
    assert seen.get("regenerate") is True, seen
