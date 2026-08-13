"""推理增量：用作「仍在推进」的实证，但绝不能混进答案。

DeepSeek 的推理模型在思考阶段发的是 ``delta.reasoning_content``，而 chat.py 此前
只读 ``delta.content`` —— 那些块被整个丢弃，用户在 7–13 秒里只看到一句静态占位符。

这里锁三条，每一条对应一个真实的失效模式：

1. 推理增量产出 ``reasoning`` 事件，且**不进** ``full_answer``。若混进去，推理过程
   （充满会被自己推翻的中间结论）会变成答案正文 —— 直接违反本产品「答案不得有
   错误或虚假信息」的准则。
2. 只有推理、没有正文时仍走空回复兜底发 ``error``。``received_first_token`` 若被
   推理置真，兜底失效，用户会永远卡在假的「正在检索…」上且没有重试按钮。
3. ``reasoning`` 事件被节流。推理可达 4000 token，逐块转发等于把 SSE 流量放大数倍，
   而前端只显示一个数字。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatSource


def _sources() -> list[ChatSource]:
    return [
        ChatSource(text_id=1, juan_num=1, chunk_text="色不異空", score=0.9, title_zh="心經"),
    ]


def _make_prepare_chat_return(sources: list[ChatSource]):
    fake_session = MagicMock()
    fake_session.id = 42
    return (
        fake_session, "https://api.example.com/v1", "fake-key", "deepseek-v4-pro",
        False, "deepseek", sources, [{"role": "user", "content": "測試"}], [],
    )


def _make_mock_httpx_client(deltas: list[dict]):
    """deltas 里每一项直接作为 OpenAI 流式的 ``delta`` 对象。

    例：{"reasoning_content": "先看心經"} / {"content": "色不異空"}
    """
    lines = [f"data: {json.dumps({'choices': [{'delta': d}]})}" for d in deltas]
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
    def __call__(self):
        class _SessCM:
            async def __aenter__(self_inner): return AsyncMock()
            async def __aexit__(self_inner, *_): return False

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


async def _run(deltas: list[dict]) -> list[dict]:
    saved: dict = {}

    async def _capture_save(*args, **kwargs):
        # _save_messages 收到的是最终落库的答案正文 —— 用它验「推理没混进答案」
        for a in args:
            if isinstance(a, str) and a:
                saved.setdefault("answer", a)
        return 99

    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock,
               return_value=_make_prepare_chat_return(_sources())), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock,
               side_effect=_capture_save), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient", _make_mock_httpx_client(deltas)):
        from app.services.chat import send_message_stream

        chunks: list[str] = []
        async for chunk in send_message_stream(
            user_id=1, message="測試", sessionmaker=_FakeSessionmaker(),
        ):
            chunks.append(chunk)
    return _events(chunks)


@pytest.mark.anyio
async def test_reasoning_never_enters_the_answer():
    """推理增量必须只产出 reasoning 事件，绝不出现在 token 里。"""
    events = await _run([
        {"reasoning_content": "先看《心經》這一段，"},
        {"reasoning_content": "但也可能該引《大般若經》，再想想。"},
        {"content": "「色不異空」出自《心經》。"},
    ])

    tokens = "".join(e["content"] for e in events if e.get("type") == "token")
    assert "再想想" not in tokens, f"推理过程混进了答案正文: {tokens!r}"
    assert "先看" not in tokens, f"推理过程混进了答案正文: {tokens!r}"
    assert tokens == "「色不異空」出自《心經》。", f"答案正文被污染: {tokens!r}"
    assert any(e.get("type") == "reasoning" for e in events), \
        f"推理增量未产出 reasoning 事件；实际: {[e.get('type') for e in events]}"


@pytest.mark.anyio
async def test_reasoning_only_still_hits_empty_completion_guard():
    """只有推理、一个正文 token 都没有 —— 空回复兜底必须照常发 error。

    若 received_first_token 被推理置真，兜底失效，用户会永远卡在假的
    「正在检索…」上，且没有重试按钮。
    """
    events = await _run([
        {"reasoning_content": "想了很久"},
        {"reasoning_content": "但什麼都沒說出來"},
    ])
    types = [e.get("type") for e in events]

    assert "token" not in types, f"不该有 token；实际: {types}"
    assert "error" in types, f"只有推理时必须落到空回复兜底发 error；实际: {types}"
    assert types.index("error") < types.index("done"), \
        f"error 必须早于 done（前端靠它离开占位符）；实际: {types}"


@pytest.mark.anyio
async def test_reasoning_events_are_throttled():
    """高频推理增量不该被逐块转发 —— 前端只显示一个数字。"""
    deltas = [{"reasoning_content": f"第{i}步。"} for i in range(200)]
    deltas.append({"content": "答案。"})
    events = await _run(deltas)

    reasoning_events = [e for e in events if e.get("type") == "reasoning"]
    assert len(reasoning_events) < 20, (
        f"200 个推理增量产出了 {len(reasoning_events)} 个事件，未生效节流"
    )
    assert reasoning_events, "节流不能把事件全吃掉"
    # 载荷是累计字符数，必须单调递增
    chars = [e["chars"] for e in reasoning_events]
    assert chars == sorted(chars), f"累计字符数应单调递增；实际: {chars}"


@pytest.mark.anyio
async def test_reasoning_frames_carry_the_text_excerpt():
    """推理帧要带上文本增量 —— 等待期「思考过程片段」的原料。

    2026-08-13 定案：削推理档位换速度已被 90 题 eval 证否（逐字保真度 −12.9pp），
    等待的 30-180 秒砍不掉，能改的只有等待的感受。推理文本是现成的可读中文，
    此前整条丢掉、只发一个字数 —— 现在随帧带出去，但只准进等待区，绝不进正文。
    """
    events = await _run([
        {"reasoning_content": "先看《心經》這一段，"},
        {"reasoning_content": "但也可能該引《大般若經》。"},
        {"content": "「色不異空」出自《心經》。"},
    ])

    reasoning_frames = [e for e in events if e.get("type") == "reasoning"]
    assert reasoning_frames, "没有 reasoning 事件"
    for f in reasoning_frames:
        assert isinstance(f.get("text"), str) and f["text"], (
            f"推理帧缺少 text 字段（前端等待区没有原料可显示）: {f!r}"
        )
    joined = "".join(f["text"] for f in reasoning_frames)
    assert "先看《心經》這一段，" in joined, f"推理文本没有透传: {joined!r}"

    # 承重不变式：文本走 reasoning 帧，绝不混进 token 正文
    tokens = "".join(e["content"] for e in events if e.get("type") == "token")
    assert tokens == "「色不異空」出自《心經》。", f"答案正文被污染: {tokens!r}"


@pytest.mark.anyio
async def test_reasoning_text_frame_is_capped_keeping_the_tail():
    """单帧文本要封顶且保尾部 —— 显示的是「正在想什么」的活窗，不是完整记录。

    上游可能在一次网络读里灌进上千字（重推理模型的常态），不封顶等于把 SSE 帧
    放大几十倍；封头不封尾则显示的永远是最旧的想法。
    """
    from app.services.chat import REASONING_TEXT_FRAME_MAX_CHARS

    big = "前面的推理。" * 800 + "最新落点在《心經》"
    events = await _run([{"reasoning_content": big}, {"content": "答案。"}])

    frames = [e for e in events if e.get("type") == "reasoning"]
    assert frames, "没有 reasoning 事件"
    for f in frames:
        assert len(f["text"]) <= REASONING_TEXT_FRAME_MAX_CHARS, (
            f"单帧 {len(f['text'])} 字，超出 {REASONING_TEXT_FRAME_MAX_CHARS} 封顶"
        )
    assert frames[0]["text"].endswith("最新落点在《心經》"), (
        f"封顶截掉了尾部（最新的想法）: ...{frames[0]['text'][-40:]!r}"
    )


@pytest.mark.anyio
async def test_phase2_log_records_reasoning_volume_and_model(caplog):
    """phase-2 日志必须带上推理字符数与模型名。

    2026-08-01 的排查里，日志只说「96.75s, 0 chars, provider=deepseek」——
    看不出这 96 秒花在哪，也看不出是 pro 还是 flash（provider 两者都是 deepseek）。
    定位因此绕了很远：先翻 Prometheus 的 model 标签才知道是 flash，再从 SSE 流里
    数 reasoning 事件才知道推理吃掉了全部预算。

    这两个字段一旦在日志里，同一个故障一眼就能断：
      "0 chars, reasoning=11826 chars, model=deepseek-v4-flash" —— 推理顶穿上限。
    """
    import logging
    with caplog.at_level(logging.INFO, logger="app.services.chat"):
        await _run([{"reasoning_content": "先看《地藏經》怎麼說"}, {"content": "答案正文"}])

    line = next((r.getMessage() for r in caplog.records if "phase-2 LLM done" in r.getMessage()), None)
    assert line is not None, "phase-2 计时日志没打出来"
    assert "reasoning=10 chars" in line, f"日志缺少推理字符数: {line}"
    assert "model=deepseek-v4-pro" in line, f"日志缺少模型名: {line}"
    # reader 标记：page_content 决定 max_tokens 2000/8000，没有它日志里量不出
    # reader 模式占比（2026-08-13 排查延迟时的观测缺口）。
    assert "reader=False" in line, f"日志缺少 reader 标记: {line}"

    # 流式路径的 prep 计时同为该次排查的缺口 —— 此前只有非流式的
    # "TIMING: _prepare_chat"，/chat/stream 的 prep 一直量不到。
    assert any("TIMING: stream prep took" in r.getMessage() for r in caplog.records), \
        "流式路径缺少 prep 计时日志"
