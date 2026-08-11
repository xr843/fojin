"""Azure Speech TTS 适配器：SSML → mp3 + 词边界时间戳。

选 Azure 的唯一理由是 word boundary 事件 —— 它让「播到哪高亮到哪」不需要
另做强制对齐。若音色试听后改用其他厂商，只需另写一个同签名的适配器，
build_audio.py 不用动（`engine` 字段就是为此预留的）。

⚠️ <phoneme alphabet="sapi"> 对 zh-CN 的支持度是本方案的**未验证前提**。
   若合成结果里「佛」仍读 fú，说明 phoneme 未生效，须改走 Custom Lexicon
   (PLS) 或换厂商 —— 这是音色闸门必须一并验通的事。
"""

from __future__ import annotations

import os
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk


class TtsError(RuntimeError):
    pass


def synthesize(
    ssml: str,
    out_path: Path,
    key: str | None = None,
    region: str | None = None,
) -> list[tuple[int, int]]:
    """把 SSML 合成为 mp3，返回词边界 [(文本字符偏移, 音频毫秒), ...]。

    文本偏移是 Azure 相对**纯文本**（SSML 标签剥离后）的偏移，不是 SSML 串偏移。
    """
    key = key or os.environ.get("AZURE_SPEECH_KEY")
    region = region or os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        raise TtsError("需要环境变量 AZURE_SPEECH_KEY 与 AZURE_SPEECH_REGION")

    cfg = speechsdk.SpeechConfig(subscription=key, region=region)
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio_cfg = speechsdk.audio.AudioOutputConfig(filename=str(out_path))
    synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=audio_cfg)

    boundaries: list[tuple[int, int]] = []

    def _on_boundary(evt) -> None:
        # audio_offset 单位是 100 纳秒 tick，转毫秒
        boundaries.append((evt.text_offset, evt.audio_offset // 10_000))

    synth.synthesis_word_boundary.connect(_on_boundary)

    result = synth.speak_ssml_async(ssml).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        detail = ""
        if result.reason == speechsdk.ResultReason.Canceled:
            c = speechsdk.SpeechSynthesisCancellationDetails(result)
            detail = f" reason={c.reason} error={c.error_details}"
        raise TtsError(f"合成失败: {result.reason}{detail}")

    boundaries.sort(key=lambda b: b[1])
    return boundaries
