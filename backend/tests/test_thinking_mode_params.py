"""思考档位参数：一个只对 DeepSeek V4 生效的开关，默认什么都不发。

2026-08-13 生产实测（同一条真实提示词、同一模型，各跑两次）：

    不带思考参数（= 上游默认 high）  首个正文字 77.1s / 187.9s，推理 5,268 / 13,908 字
    reasoning_effort=low            首个正文字 29.3s / 15.7s，推理 1,888 / 1,327 字
    thinking=disabled               首个正文字  1.0s /  1.2s，推理 0 字

等待时间几乎全是隐藏推理（正文要等推理吐完才开始），而我们的请求体里一个档位
参数都没有 —— 每道题都跑上游默认的最高档，连 max_tokens=64 的会话标题也是。

这里锁四条：

1. **不配置就什么都不发**。默认必须与今天的线上行为逐字节相同，否则这个开关
   本身就成了一次未经 eval 的答案改动。见 answer-fidelity-is-the-bar。
2. **只对 deepseek-v4* 下发**。除 Anthropic 外的七家共用同一个 OpenAI 兼容
   body builder，把 DeepSeek 私有字段发给 OpenAI / Gemini 会被 400 拒掉 ——
   那位自带 Key 的用户会直接问不出话来。
3. **非法档位当作没配**。.env 里一个笔误不能让全站每一次问答都 400。
4. **会话标题一律关思考**。给一个 5-10 字的标题跑最高档推理是纯浪费，且它
   不进答案，没有质量风险。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_client import thinking_params


class TestThinkingParams:
    def test_no_effort_sends_nothing(self):
        """默认（未配置）必须与今天的线上行为完全一致 —— 一个字段都不加。"""
        assert thinking_params("deepseek-v4-pro", None) == {}
        assert thinking_params("deepseek-v4-pro", "") == {}

    def test_low_effort_enables_thinking(self):
        assert thinking_params("deepseek-v4-pro", "low") == {
            "thinking": {"type": "enabled"},
            "reasoning_effort": "low",
        }

    def test_high_and_max_pass_through(self):
        for effort in ("high", "max"):
            assert thinking_params("deepseek-v4-flash", effort) == {
                "thinking": {"type": "enabled"},
                "reasoning_effort": effort,
            }

    def test_off_disables_thinking(self):
        """关闭用的是 thinking.type=disabled，不是 reasoning_effort=none —— 后者
        是 Anthropic 格式，DeepSeek 的 OpenAI 兼容端点不认。"""
        assert thinking_params("deepseek-v4-pro", "off") == {"thinking": {"type": "disabled"}}

    @pytest.mark.parametrize("model", [
        "qwen3.7-plus", "kimi-k3", "glm-5.2", "gpt-5.6-sol",
        "gemini-3.6-flash", "doubao-seed-2-1-pro-260628", "deepseek-chat",
    ])
    def test_other_providers_get_nothing(self, model):
        """⭐ 本文件最重要的一条：thinking / reasoning_effort 是 DeepSeek V4 的私有
        字段。七家共用一个 body builder，漏给别人就是把那位用户的问答打成 400。"""
        for effort in ("low", "high", "max", "off"):
            assert thinking_params(model, effort) == {}

    def test_invalid_effort_is_ignored(self):
        """.env 笔误不能让全站问答 400 —— 当作没配，退回上游默认。"""
        assert thinking_params("deepseek-v4-pro", "lowest") == {}
        assert thinking_params("deepseek-v4-pro", "none") == {}

    def test_model_none_is_safe(self):
        assert thinking_params(None, "low") == {}


class TestTitleGenerationDisablesThinking:
    """会话标题：max_tokens=64 却在跑最高档推理，纯浪费，且不进答案。"""

    @pytest.mark.asyncio
    async def test_title_request_body_disables_thinking(self):
        from app.services.chat import _generate_session_title

        captured = {}

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(
            return_value={"choices": [{"message": {"content": "般若与智慧"}}]}
        )

        class _Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): return False

            async def post(self, url, headers=None, json=None):
                captured.update(json or {})
                return mock_resp

        with patch("app.services.chat._build_llm_http_client",
                   new=AsyncMock(return_value=_Client())):
            title = await _generate_session_title(
                "https://api.deepseek.com/v1", "k", "deepseek-v4-pro",
                "「般若」和智慧有什么不同？", "般若体绝名字……", provider="deepseek",
            )

        assert title == "般若与智慧"
        assert captured.get("thinking") == {"type": "disabled"}, (
            f"标题生成仍在跑思考模式，请求体={json.dumps(captured, ensure_ascii=False)[:200]}"
        )


def _capture_stream_client(captured: dict):
    """替身 httpx.AsyncClient：记下流式请求体，回一个只有一块正文的流。"""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    async def aiter_lines():
        yield "data: " + json.dumps({"choices": [{"delta": {"content": "色不異空"}}]})
        yield "data: [DONE]"

    mock_resp.aiter_lines = aiter_lines

    class _StreamCM:
        async def __aenter__(self): return mock_resp
        async def __aexit__(self, *_): return False

    class _ClientInstance:
        def stream(self, *args, **kwargs):
            captured.update(kwargs.get("json") or {})
            return _StreamCM()

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


def _prepare_chat_return():
    from app.schemas.chat import ChatSource

    fake_session = MagicMock()
    fake_session.id = 42
    return (
        fake_session, "https://api.deepseek.com/v1", "fake-key", "deepseek-v4-pro",
        False, "deepseek",
        [ChatSource(text_id=1, juan_num=1, chunk_text="色不異空", score=0.9, title_zh="心經")],
        [{"role": "user", "content": "測試"}], [],
    )


async def _run_stream_capturing_body(effort: str) -> dict:
    captured: dict = {}
    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock,
               return_value=_prepare_chat_return()), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.llm_client.settings.chat_reasoning_effort", effort), \
         patch("app.services.chat.httpx.AsyncClient", _capture_stream_client(captured)):
        from app.services.chat import send_message_stream

        async for _ in send_message_stream(
            user_id=1, message="測試", sessionmaker=_FakeSessionmaker(),
        ):
            pass
    return captured


class TestAnswerPathHonoursSetting:
    """正式问答走配置项；**默认必须与今天的线上行为逐字节相同**。"""

    @pytest.mark.asyncio
    async def test_default_sends_no_thinking_fields(self):
        body = await _run_stream_capturing_body("")
        assert "thinking" not in body and "reasoning_effort" not in body, (
            f"未配置档位时不应改变请求体，实际={json.dumps(body, ensure_ascii=False)[:200]}"
        )

    @pytest.mark.asyncio
    async def test_configured_effort_reaches_the_request(self):
        body = await _run_stream_capturing_body("low")
        assert body.get("thinking") == {"type": "enabled"}
        assert body.get("reasoning_effort") == "low"
