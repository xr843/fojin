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
        # ⚠️ 必须显式关掉：默认为 True 时会去编译 BigVGAN 的融合 kernel，而构建
        # 参数里带 `-gencode arch=compute_70`（Volta），新版 CUDA 工具链已不支持，
        # 实测报 `nvcc fatal: Unsupported gpu architecture 'compute_70'`。
        # 它会优雅降级，但每次加载都白试一次并刷一屏错误。
        use_cuda_kernel=False,
    )
    return _model


def synthesize(
    annotated_text: str,
    out_path: Path,
    spk_audio_prompt: Path,
    lang: str = "zh",
    duration_factor: float = 1.0,
    text_normalization: bool = False,
) -> None:
    """把已带 ``<字|PINYIN>`` 标注的文本合成为 wav。

    参数与 tts_azure.synthesize 刻意不同（那边吃 SSML，这边吃标注文本）——
    两者的共同契约是「文本进、音频文件出」，由 build_audio.py 按 engine 分派。

    ⚠️ ``text_normalization`` **默认关闭**，与上游默认值相反。实测（2026-08-11）
    开启时它会把繁体转成简体：``如是我聞：一時，`` → ``如是我闻,一时,``，
    而 CBETA 语料是繁体。多数繁简转换对读音无害（聞/闻 同音），但简化字合并了
    不同的字，会改读音 —— 如 ``乾闥婆``(qián) → ``干闼婆``（「干」可读 gān）、
    ``髮``(fà)/``發``(fā) 都变 ``发``。对一个专做繁体语料的平台，这是不可接受的
    静默改写。实测关闭后速度无差异（稳态 RTF 均为 2.78）。

    ⚠️ 副作用：关掉归一化后全角标点（「」『』：。）原样进模型，其韵律处理
    效果未经试听确认 —— 若发现停顿异常，应由调用方在送入前自行折算标点，
    而**不要**重新打开归一化（那会连繁体一起改掉）。

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
        text_normalization=text_normalization,
        verbose=False,
    )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise TtsError(f"合成未产出音频: {out_path}")
