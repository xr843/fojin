"""在线读诵音频 API。

本仓测试不连真库，故这里覆盖两件不需要 DB 的事：
* service 把 ORM 行拼成响应字典的形状 —— 尤其 cues 必须按 time_ms 升序
  （前端 findCueIndex 是二分查找，乱序会让高亮跳到别处）
* 无音频时端点返回 404 而不是 200 + 空对象 —— 前端据此决定不渲染读诵按钮
"""

from unittest.mock import AsyncMock, MagicMock

from app.services.audio import build_audio_payload


def _cue(char_start: int, char_end: int, time_ms: int, kind: str = "prose") -> MagicMock:
    m = MagicMock()
    m.char_start, m.char_end, m.time_ms, m.kind = char_start, char_end, time_ms, kind
    return m


def _audio(cues: list[MagicMock]) -> MagicMock:
    m = MagicMock()
    m.voice_id = "Chinese (Mandarin)_Lyrical_Voice"
    m.engine = "minimax"
    m.audio_path = "9/1-a328034b.mp3"
    m.duration_ms = 108_035
    m.content_hash = "a328034b" + "0" * 56
    m.cues = cues
    return m


def test_payload_sorts_cues_by_time() -> None:
    """cue 必须按时间升序 —— 前端 findCueIndex 是二分查找。"""
    audio = _audio([_cue(20, 30, 5000), _cue(0, 10, 0), _cue(10, 20, 2500)])
    payload = build_audio_payload(audio)
    assert [c["time_ms"] for c in payload["cues"]] == [0, 2500, 5000]
    assert [c["char_start"] for c in payload["cues"]] == [0, 10, 20]


def test_payload_url_is_rooted_at_audio() -> None:
    """URL 必须是 /audio/ 下的绝对路径 —— 由宿主机 nginx 直出，不经后端。"""
    assert build_audio_payload(_audio([]))["url"] == "/audio/9/1-a328034b.mp3"


def test_payload_carries_engine_for_frontend_labelling() -> None:
    """前端据 engine 决定是否标「AI 合成朗读」—— 真人录音将来用 engine='human'。"""
    payload = build_audio_payload(_audio([]))
    assert payload["engine"] == "minimax"
    assert payload["voice_id"] == "Chinese (Mandarin)_Lyrical_Voice"


def test_payload_keeps_cue_kind() -> None:
    """kind 要传到前端 —— 读经名/译者署名时是否高亮由前端决定。"""
    payload = build_audio_payload(_audio([_cue(0, 8, 0, "head"), _cue(8, 16, 1996, "byline")]))
    assert [c["kind"] for c in payload["cues"]] == ["head", "byline"]


async def test_endpoint_404_when_no_audio(client) -> None:
    """没有音频的卷必须 404，前端据此不渲染读诵按钮。

    fixture ``client``（conftest.py:64）已把 get_db 覆盖成 yield None，
    所以只要 get_juan_audio 被 mock 掉、不碰 DB，本用例即可跑通。
    pytest.ini 设了 asyncio_mode=auto，不需要 @pytest.mark 装饰器。
    """
    from app.api import texts as texts_api

    original = texts_api.get_juan_audio
    texts_api.get_juan_audio = AsyncMock(return_value=None)
    try:
        resp = await client.get("/api/texts/999999/juans/1/audio")
        assert resp.status_code == 404
    finally:
        texts_api.get_juan_audio = original


async def test_catalog_endpoint_returns_grouped_items(client) -> None:
    """索引页与经典详情页共用这一个端点，形状必须稳定。"""
    from app.api import audio as audio_api

    original = audio_api.list_available_audio
    audio_api.list_available_audio = AsyncMock(
        return_value=[
            {
                "text_id": 9,
                "title_zh": "般若波羅蜜多心經",
                "translator": "玄奘",
                "dynasty": "唐",
                "taisho_id": "T0251",
                "engine": "minimax",
                "juan_count": 1,
                "total_duration_ms": 101_363,
                "juans": [{"juan_num": 1, "duration_ms": 101_363, "url": "/audio/9/1-7891dd17.mp3"}],
            }
        ]
    )
    try:
        resp = await client.get("/api/audio/available")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title_zh"] == "般若波羅蜜多心經"
        assert body["items"][0]["juans"][0]["url"] == "/audio/9/1-7891dd17.mp3"
    finally:
        audio_api.list_available_audio = original


async def test_catalog_endpoint_is_empty_not_404_when_nothing_available(client) -> None:
    """空目录回 200 + 空数组。404 会让索引页显示成「页面不存在」。"""
    from app.api import audio as audio_api

    original = audio_api.list_available_audio
    audio_api.list_available_audio = AsyncMock(return_value=[])
    try:
        resp = await client.get("/api/audio/available")
        assert resp.status_code == 200
        assert resp.json() == {"total": 0, "items": []}
    finally:
        audio_api.list_available_audio = original


async def test_endpoint_returns_payload_when_audio_exists(client) -> None:
    """有音频时回 200，且 text_id/juan_num 由路径参数带回。"""
    from app.api import texts as texts_api

    original = texts_api.get_juan_audio
    texts_api.get_juan_audio = AsyncMock(
        return_value={
            "url": "/audio/9/1-a328034b.mp3",
            "voice_id": "Chinese (Mandarin)_Lyrical_Voice",
            "engine": "minimax",
            "duration_ms": 108_035,
            "cues": [{"char_start": 0, "char_end": 8, "time_ms": 0, "kind": "head"}],
        }
    )
    try:
        resp = await client.get("/api/texts/9/juans/1/audio")
        assert resp.status_code == 200
        body = resp.json()
        assert body["text_id"] == 9
        assert body["juan_num"] == 1
        assert body["url"] == "/audio/9/1-a328034b.mp3"
        assert body["cues"][0]["kind"] == "head"
    finally:
        texts_api.get_juan_audio = original
