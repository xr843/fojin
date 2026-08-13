"""流式路径的上游 HTTP 错误必须原样浮出来，别被自己的错误处理吞掉。

2026-08-13 生产实测：某位自带 Key 的用户连吃 8 次 401，每次 0.4 秒拿到同一句
「抱歉，AI 服务暂时不可用，请稍后重试。」（正好 20 字）。日志里是
``ERROR app.services.chat: LLM stream failed`` 带 traceback，而 traceback 的最后
一行正是错误处理器自己那句 ``resp_body = exc.response.text[...]``。

成因：``exc.response`` 是一个**流式且从未 read 过**的响应，取 ``.text`` 抛
``httpx.ResponseNotRead``，于是处理 401 的分支自己崩了，掉进最外层
``except Exception``，``_byok_error_message()`` 与 ``byok_config`` 归因码根本没机会执行。

后果有两层：那位用户以为是佛津坏了而不是自己的 Key 无效；#1119 那套断流归因
（byok_config / upstream_http_429 …）在整条流式路径上是瞎的。

⚠️ 写这类替身时必须让响应**真的**处于未读状态（用异步生成器当 content）。
传 bytes 的话响应已读，``.text`` 正常，测试会假绿 —— 见 fixture-shells-hide-real-bugs。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.schemas.chat import ChatSource


def _unread_401() -> httpx.HTTPStatusError:
    """造一个与生产同构的异常：401，且 body 尚未读取。"""
    req = httpx.Request("POST", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")

    async def _body():
        yield b'{"error":{"message":"Invalid API-key provided.","code":"invalid_api_key"}}'

    resp = httpx.Response(401, content=_body(), request=req)
    # 自证：此刻取 .text 必须抛 ResponseNotRead，否则这个替身没有复现真实条件。
    with pytest.raises(httpx.ResponseNotRead):
        _ = resp.text
    return httpx.HTTPStatusError("Client error '401 Unauthorized'", request=req, response=resp)


def _client_raising(exc: Exception):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=exc)

    async def aiter_lines():
        if False:  # pragma: no cover - 永远到不了，raise_for_status 先抛
            yield ""

    mock_resp.aiter_lines = aiter_lines

    class _StreamCM:
        async def __aenter__(self): return mock_resp
        async def __aexit__(self, *_): return False

    class _ClientInstance:
        def stream(self, *a, **kw): return _StreamCM()

    class _ClientCM:
        async def __aenter__(self): return _ClientInstance()
        async def __aexit__(self, *_): return False

    return MagicMock(return_value=_ClientCM())


class _FakeSessionmaker:
    def __call__(self):
        class _SessCM:
            async def __aenter__(self_inner): return AsyncMock()
            async def __aexit__(self_inner, *_): return False

        return _SessCM()


def _prepare_chat_return(is_byok: bool):
    fake_session = MagicMock()
    fake_session.id = 42
    return (
        fake_session, "https://dashscope.aliyuncs.com/compatible-mode/v1", "bad-key",
        "qwen3.7-plus", is_byok, "dashscope",
        [ChatSource(text_id=1, juan_num=1, chunk_text="色不異空", score=0.9, title_zh="心經")],
        [{"role": "user", "content": "測試"}], [],
    )


async def _collect_events(is_byok: bool, exc: Exception) -> list[dict]:
    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock,
               return_value=_prepare_chat_return(is_byok)), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", _client_raising(exc)):
        from app.services.chat import send_message_stream

        out: list[dict] = []
        async for chunk in send_message_stream(
            user_id=1, message="測試", sessionmaker=_FakeSessionmaker(),
        ):
            for line in chunk.splitlines():
                if line.startswith("data: "):
                    try:
                        out.append(json.loads(line[len("data: "):]))
                    except json.JSONDecodeError:
                        pass
        return out


@pytest.mark.asyncio
async def test_byok_401_surfaces_key_error_not_generic_outage():
    events = await _collect_events(is_byok=True, exc=_unread_401())
    errors = [e for e in events if e.get("type") == "error"]
    assert errors, f"没有 error 事件，收到的是 {events!r:.300}"
    err = errors[-1]

    assert err.get("code") == "byok_config", (
        f"归因码丢了（断流统计会把 Key 配错记成服务故障）：{err!r}"
    )
    assert err["message"] != "抱歉，AI 服务暂时不可用，请稍后重试。", (
        "用户又拿到了那句通用文案 —— 错误处理器很可能仍在读未 read 的流式 body"
    )
    assert "Key" in err["message"] or "模型" in err["message"] or "余额" in err["message"], (
        f"提示没有说清到底哪里配错了：{err['message']!r}"
    )


@pytest.mark.asyncio
async def test_platform_upstream_http_error_keeps_its_status_code():
    """平台侧（非 BYOK）的上游错误同样不能被吞：归因码要带上状态码。"""
    req = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")

    async def _body():
        yield b'{"error":{"message":"Rate limit reached."}}'

    resp = httpx.Response(429, content=_body(), request=req)
    exc = httpx.HTTPStatusError("Client error '429'", request=req, response=resp)

    events = await _collect_events(is_byok=False, exc=exc)
    errors = [e for e in events if e.get("type") == "error"]
    assert errors, f"没有 error 事件，收到的是 {events!r:.300}"
    assert errors[-1].get("code") == "upstream_http_429", (
        f"429 被归因成了别的东西：{errors[-1]!r}"
    )
