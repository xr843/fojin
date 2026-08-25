"""``retrieved`` 事件：检索完成、生成开始之前告诉前端召回了什么。

改动前，从提问到第一个字之间的几秒里前端只有一句静态文案「正在检索经文并生成
回答…」，没有任何证据表明真的检索到了东西 —— 而召回其实在生成之前就完成了，
只是完整的 ``sources`` 要等答案全部生成完才发。

这里锁三件事：

1. ``retrieved`` 在第一个 ``token`` **之前**发出（否则等待期依旧是白等）
2. 完整的 ``sources`` **仍然是最后一个数据事件**（「先论点后论据」是刻意设计；
   而且提前发 sources 会让前端的 injectCitationLinks 在残缺的流式文本上改写经名）
3. ``titles`` 去重且至多 3 条，``count`` 仍是全量数字
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatSource


def _sources() -> list[ChatSource]:
    """5 条召回、4 个不同经名（心经出现两次，用来验去重）。"""
    return [
        ChatSource(text_id=1, juan_num=1, chunk_text="色不异空", score=0.95, title_zh="心经"),
        ChatSource(text_id=1, juan_num=1, chunk_text="空不异色", score=0.93, title_zh="心经"),
        ChatSource(text_id=2, juan_num=403, chunk_text="色即是空", score=0.9, title_zh="大般若经"),
        ChatSource(text_id=3, juan_num=1, chunk_text="一即一切", score=0.88, title_zh="华严经"),
        ChatSource(text_id=4, juan_num=1, chunk_text="诸法实相", score=0.85, title_zh="法华经"),
    ]


def _make_prepare_chat_return(sources: list[ChatSource]):
    fake_session = MagicMock()
    fake_session.id = 42
    return (
        fake_session, "https://api.example.com/v1", "fake-key", "test-model",
        False, "openai", sources, [{"role": "user", "content": "测试"}], [],
    )


def _make_mock_httpx_client(tokens: list[str]):
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


async def _run_stream(sources: list[ChatSource]) -> list[dict]:
    with patch("app.services.chat._prepare_chat", new_callable=AsyncMock,
               return_value=_make_prepare_chat_return(sources)), \
         patch("app.services.chat._save_messages", new_callable=AsyncMock, return_value=99), \
         patch("app.services.chat._mark_attachments_consumed", new_callable=AsyncMock), \
         patch("app.services.chat.httpx.AsyncClient",
               _make_mock_httpx_client(["色不异空", "，是说"])):
        from app.services.chat import send_message_stream

        chunks: list[str] = []
        async for chunk in send_message_stream(
            user_id=1, message="测试", sessionmaker=_FakeSessionmaker(),
        ):
            chunks.append(chunk)
    return _events(chunks)


@pytest.mark.anyio
async def test_retrieved_precedes_first_token():
    """等待期要有实证：``retrieved`` 必须在第一个 ``token`` 之前。"""
    events = await _run_stream(_sources())
    types = [e.get("type") for e in events]

    assert "retrieved" in types, f"未发出 retrieved 事件；实际: {types}"
    assert "token" in types, f"用例前提失败——没有 token；实际: {types}"
    assert types.index("retrieved") < types.index("token"), (
        f"retrieved 必须早于第一个 token，否则等待期依旧无证据；实际顺序: {types}"
    )


@pytest.mark.anyio
async def test_full_sources_still_last():
    """完整 sources 仍排在所有 token 之后 —— 「先论点后论据」是刻意设计，
    且提前发会让前端在残缺流式文本上改写经名。"""
    events = await _run_stream(_sources())
    types = [e.get("type") for e in events]

    assert "sources" in types, f"未发出 sources；实际: {types}"
    last_token = max(i for i, t in enumerate(types) if t == "token")
    assert types.index("sources") > last_token, (
        f"sources 必须在最后一个 token 之后；实际顺序: {types}"
    )
    # retrieved 是轻量事件，绝不能顺手把完整 sources 塞进去
    retrieved = next(e for e in events if e.get("type") == "retrieved")
    assert "sources" not in retrieved, f"retrieved 不该携带完整 sources: {retrieved}"


@pytest.mark.anyio
async def test_retrieved_payload_dedupes_and_caps_titles():
    """count 是全量数字；titles 去重后至多 3 条。"""
    events = await _run_stream(_sources())
    retrieved = next(e for e in events if e.get("type") == "retrieved")

    assert retrieved["count"] == 5, f"count 应为全量 5；实际 {retrieved['count']}"
    titles = retrieved["titles"]
    assert titles == ["心经", "大般若经", "华严经"], (
        f"titles 应按召回顺序去重并截断到 3 条；实际 {titles}"
    )


@pytest.mark.anyio
async def test_no_retrieved_event_when_nothing_retrieved():
    """零召回时不发 retrieved —— 「已检索 0 部经典」是反效果的。"""
    events = await _run_stream([])
    types = [e.get("type") for e in events]
    assert "retrieved" not in types, f"零召回不该发 retrieved；实际: {types}"


@pytest.mark.anyio
async def test_retrieved_carries_light_refs_for_early_source_chips():
    """等待期（首字前常 30–180 秒）就能点开原文：``retrieved`` 带轻量 ``refs``。

    ``refs`` 只有定位字段（text_id / juan_num / chunk_index / title_zh），**没有**
    chunk_text —— 完整 ``sources`` 仍是最后一个数据事件（见上一条用例），前端也不会
    把 refs 喂给 injectCitationLinks。按 (text_id, juan_num) 去重、保持召回顺序、
    至多 8 条。
    """
    events = await _run_stream(_sources())
    retrieved = next(e for e in events if e.get("type") == "retrieved")

    refs = retrieved["refs"]
    assert [(r["text_id"], r["juan_num"]) for r in refs] == [(1, 1), (2, 403), (3, 1), (4, 1)]
    assert [r["title_zh"] for r in refs] == ["心经", "大般若经", "华严经", "法华经"]
    for r in refs:
        assert set(r) == {"text_id", "juan_num", "chunk_index", "title_zh"}, r
    assert "chunk_text" not in json.dumps(retrieved, ensure_ascii=False)


@pytest.mark.anyio
async def test_retrieved_refs_capped_at_eight():
    many = [
        ChatSource(text_id=i, juan_num=1, chunk_text="x", score=0.5, title_zh=f"经{i}")
        for i in range(1, 13)
    ]
    events = await _run_stream(many)
    retrieved = next(e for e in events if e.get("type") == "retrieved")
    assert len(retrieved["refs"]) == 8
    assert retrieved["count"] == 12
