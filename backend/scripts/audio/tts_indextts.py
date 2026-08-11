"""IndexTTS-2.5 适配器：标注文本 → wav。

与 tts_azure.py 是同层的可替换实现（`text_audio.engine` 字段区分二者）。
选它而非云 TTS 的三个理由：

1. **读音控制是原生通道**。IndexTTS 2.5 支持 ``<字|PINYIN>`` 标注
   （官方例：``他在银<行|XING2>里<行|HANG2>走了半天``），拼音直接进模型，
   不像 SSML ``<phoneme>`` 那样是「请厂商前端照办」。
2. **零账号零费用**，本机 RTX 4060 Laptop 8GB 即可（模型自动进 low-VRAM 模式，
   见 infer_v2_5.py 的 ``total_vram_gb < 10.0`` 分支）。
3. 支持 ``duration_factor`` 调语速（0.5x–2.0x）—— 诵经宜慢。

⚠️ 它是**零样本声音克隆**模型，没有内置音色，每次合成都要一段参考人声
   （``spk_audio_prompt``，5~10 秒即可）。参考音的授权由调用方负责。

⚠️ 不产出词级时间戳。这不影响本项目 —— cue 时间由「逐句合成 + 累计各句时长」
   得到（见 build_audio.py），本就不依赖词边界。

⚠️ 模型受 bilibili Model Use License Agreement 约束，不是 MIT/Apache。
   见 ``$INDEXTTS_DIR/LICENSE_ZH.txt``。
"""

from __future__ import annotations

import os
from pathlib import Path

# IndexTTS 装在 fojin 仓库之外（它是独立第三方项目，且模型 5.5 GB）。
# 用环境变量指路，默认取常用位置。
INDEXTTS_DIR = Path(os.environ.get("INDEXTTS_DIR", Path.home() / "projects" / "index-tts"))

_model = None


class TtsError(RuntimeError):
    pass


def vocab_path() -> Path:
    """IndexTTS 的合法拼音音节表，供 g2p.to_indextts_text 过滤用。"""
    return INDEXTTS_DIR / "checkpoints" / "pinyin.vocab"


def load_model(use_bf16: bool = True):
    """惰性加载模型。5.5 GB 权重，进程内只加载一次。

    bf16 把驻留显存从约 4.3 GB 降到约 2.1 GB —— 8 GB 卡上留出充足余量。
    ``use_qwen_emo=False``（默认）省下 1.2 GB 的情感文本模型，我们用不到。
    """
    global _model
    if _model is not None:
        return _model
    if not INDEXTTS_DIR.exists():
        raise TtsError(f"找不到 IndexTTS 安装目录: {INDEXTTS_DIR}（设 INDEXTTS_DIR 环境变量）")
    ckpt = INDEXTTS_DIR / "checkpoints"
    if not (ckpt / "config.yaml").exists():
        raise TtsError(f"模型未下载完整: {ckpt}/config.yaml 不存在")

    import sys

    sys.path.insert(0, str(INDEXTTS_DIR))
    from indextts.infer_v2_5 import IndexTTS2

    _model = IndexTTS2(
        cfg_path=str(ckpt / "config.yaml"),
        model_dir=str(ckpt),
        use_bf16=use_bf16,
        use_qwen_emo=False,
    )
    return _model


def synthesize(
    annotated_text: str,
    out_path: Path,
    spk_audio_prompt: Path,
    lang: str = "zh",
    duration_factor: float = 1.0,
) -> None:
    """把已带 ``<字|PINYIN>`` 标注的文本合成为 wav。

    参数与 tts_azure.synthesize 刻意不同（那边吃 SSML，这边吃标注文本）——
    两者的共同契约是「文本进、音频文件出」，由 build_audio.py 按 engine 分派。

    输出 wav 而非 mp3：逐句分片先留 wav，整卷拼接后一次性编码成 mp3，
    比每片各编一次少一轮有损压缩。
    """
    if not spk_audio_prompt.exists():
        raise TtsError(f"参考音频不存在: {spk_audio_prompt}")
    model = load_model()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    model.infer(
        spk_audio_prompt=str(spk_audio_prompt),
        text=annotated_text,
        output_path=str(out_path),
        lang=lang,
        duration_factor=duration_factor,
        verbose=False,
    )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise TtsError(f"合成未产出音频: {out_path}")
