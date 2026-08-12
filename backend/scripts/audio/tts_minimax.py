"""MiniMax Speech (T2A v2) 适配器：文本 → mp3。

与 tts_indextts.py / tts_azure.py 同层可替换（`text_audio.engine` 字段区分）。

选它的理由（2026-08-12）：

1. **内置专业音色，不是零样本克隆**。IndexTTS 那轮的诊断结论是「合成质量本身
   不足」——把文言换成白话也只有 74%（干净现代汉语应有 90%+）。零样本克隆把
   误差叠了两层：模型本身 + 从十几秒参考音里猜音色。内置音色没有第二层，
   也没有声音权风险。
2. **中文榜首**。Artificial Analysis Speech Arena 与 HuggingFace TTS Arena 双榜第一。
3. ⭐ **发音词典是全局参数，不改动正文**。IndexTTS 要在文本里插 ``<佛|FO2>``；
   MiniMax 用请求体里的 ``pronunciation_dict.tone``，正文一个字不动 ——
   cue 的字符坐标因此天然安全。
4. 无本地安装、无 GPU、无 20 GB 权重。金剛經全卷约 ¥2.5。

API 文档：https://platform.minimaxi.com/docs/api-reference/speech-t2a-http
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

API_URL = "https://api.minimaxi.com/v1/t2a_v2"
API_URL_BACKUP = "https://api-bj.minimaxi.com/v1/t2a_v2"

DEFAULT_MODEL = "speech-2.8-hd"
# 单次请求文本上限 10,000 字符（官方）。本流水线逐句合成，远不会触及。
MAX_CHARS = 10_000


class TtsError(RuntimeError):
    pass


def synthesize(
    text: str,
    out_path: Path,
    voice_id: str,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    speed: float = 1.0,
    emotion: str = "neutral",
    pronunciation: list[str] | None = None,
    audio_format: str = "mp3",
    timeout: int = 120,
) -> dict:
    """合成一段文本为音频文件，返回 ``extra_info``（含时长、计费字符数等）。

    ``pronunciation`` 传 ``g2p.to_minimax_dict()`` 的输出，形如
    ``["般若/(bo1)(re3)", "佛/(fo2)"]``。**正文不做任何改写。**
    """
    key = api_key or os.environ.get("MINIMAX_API_KEY")
    if not key:
        raise TtsError("需要 MINIMAX_API_KEY（环境变量或参数）")
    if len(text) > MAX_CHARS:
        raise TtsError(f"单次请求文本上限 {MAX_CHARS} 字符，实际 {len(text)}")

    body: dict = {
        "model": model,
        "text": text,
        "stream": False,
        # emotion 固定 neutral：诵经要平稳。使用者试听时明确提过
        # 「不要有些个别地方突然加重或提高音调」。
        "voice_setting": {
            "voice_id": voice_id,
            "speed": speed,
            "vol": 1.0,
            "pitch": 0,
            "emotion": emotion,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": audio_format,
            "channel": 1,
        },
    }
    if pronunciation:
        body["pronunciation_dict"] = {"tone": pronunciation}

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)

    base = payload.get("base_resp", {})
    if base.get("status_code") != 0:
        raise TtsError(f"MiniMax 返回错误 {base.get('status_code')}: {base.get('status_msg')}")

    audio_hex = (payload.get("data") or {}).get("audio")
    if not audio_hex:
        raise TtsError(f"响应中没有音频数据: {json.dumps(payload)[:200]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 官方：非流式响应的音频为 hex 编码
    out_path.write_bytes(bytes.fromhex(audio_hex))
    return payload.get("extra_info", {})


def list_voices(api_key: str | None = None, timeout: int = 60) -> list[dict]:
    """取账号可用的音色列表（系统音色 + 自有克隆音色）。"""
    key = api_key or os.environ.get("MINIMAX_API_KEY")
    if not key:
        raise TtsError("需要 MINIMAX_API_KEY")
    req = urllib.request.Request(
        "https://api.minimaxi.com/v1/get_voice",
        data=json.dumps({"voice_type": "all"}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)
