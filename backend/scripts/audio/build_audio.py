"""合成编排：正文 → 结构分段 → 逐句合成 → 拼接 → mp3 + cues.json。

用法::

    cd backend
    export MINIMAX_API_KEY=...            # 或 --key-file 指向密钥文件
    python -m scripts.audio.build_audio --manifest scripts/audio/manifest.yml

产物落在 ``out/audio/{text_id}/{juan}-{hash8}.{mp3,cues.json}``，
由 ``import_audio.py`` 入库、由 rsync 上传到生产静态目录。

⚠️ 音频绝不进 git：一部经十几 MB，而 .pre-commit-config.yaml 设了
   check-added-large-files --maxkb=500。out/ 已在 .gitignore。

设计要点（详见技能 buddhist-sutra-tts）：

* **逐句合成**，不是整段一次。三个理由：整段合成语速会漂（实测后/前 1.09
  → 逐句 0.96）；cue 时间戳由各句时长累计而来，不需另做强制对齐；
  孤立短句会被 TTS 当成强调话语（「舍利子！」独立成段时听感突兀）。
* **分片用 WAV 无损**，拼接后统一转 MP3，避免 MP3 直接拼的接缝。
* **发音词典是全局请求参数**，正文一个字不改 —— cue 坐标因此天然安全。
* ``normalize_for_tts`` 只作用于送进模型的字符串（全角空格→逗号、
  呼格感叹号→逗号），原文与坐标不受影响。
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

import yaml
from scripts.audio.g2p import to_minimax_dict
from scripts.audio.segment import normalize_for_tts, split_content
from scripts.audio.tts_minimax import synthesize

DEFAULT_API = "https://fojin.app/api"
# ⚠️ 必须带 User-Agent：Cloudflare 对 urllib 默认 UA 直接回 403，
#    且报错里看不出是被挡的。
_UA = {"User-Agent": "fojin-audio-pipeline/1.0"}

# mono 32 kHz 的口语，64k 与 128k 听感无差，体积减半（心經 1.6 MB → 793 KB）。
# 长经差别更要命：壇經一卷 134 分钟，128k 要 63 MB。
DEFAULT_BITRATE = "64k"


def log(*a: object) -> None:
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def fetch_juan(api_base: str, text_id: int, juan: int) -> str:
    req = urllib.request.Request(f"{api_base}/texts/{text_id}/juans/{juan}", headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("content") or ""


def wav_ms(path: Path) -> int:
    with contextlib.closing(wave.open(str(path))) as w:
        return int(w.getnframes() / w.getframerate() * 1000)


def concat_to_mp3(parts: list[Path], out_path: Path, bitrate: str = DEFAULT_BITRATE) -> None:
    """WAV 分片无损拼接后一次性编码为 MP3。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        for p in parts:
            fh.write(f"file '{p.resolve()}'\n")
        lst = fh.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
             "-c:a", "libmp3lame", "-b:a", bitrate, "-ar", "32000", "-ac", "1", str(out_path)],
            check=True, capture_output=True,
        )
    finally:
        Path(lst).unlink(missing_ok=True)


def synth_hash_of(cfg: dict, raw: str, pron: list[str]) -> str:
    """**合成身份** —— 只由影响波形的参数决定，给 ``.parts`` 目录命名。

    ⚠️ 字段名与取值必须与 2026-08-12 之前的单层 fingerprint **逐字节一致**。
    动一个字，已合成的 WAV 分片就会失联、断点续传落空、重新调 API ——
    而 MiniMax 是非确定性的（实测同句同参数三次 8.01/8.82/9.30 秒，
    极差 14.8%），重合成等于把使用者逐轮听审通过的版本扔掉重赌。

    刻意**不含任何编码参数**：换码率不该让人重新付费合成。
    """
    fingerprint = json.dumps(
        {
            "text": raw,
            "pron": pron,
            "voice": cfg["voice_id"],
            "model": cfg.get("model", "speech-2.8-hd"),
            "speed": cfg.get("speed", 1.0),
            "pipeline": 2,   # 分段/规范化规则改动时手动 +1
        },
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def content_hash_of(synth_hash: str, cfg: dict) -> str:
    """**成品身份** —— 合成身份叠上编码参数，给 mp3 命名，也是入库的 content_hash。

    文件名带它的前 8 位，是为了「重生成 = 新 URL」。``/audio/`` 段发的是
    ``Cache-Control: immutable, max-age=31536000``，同名文件在 Cloudflare
    边缘能活一年 —— 编码参数变了却不换名，等于改了个寂寞。
    """
    fingerprint = json.dumps(
        {
            "synth": synth_hash,
            "bitrate": cfg.get("bitrate", DEFAULT_BITRATE),
            "format": cfg.get("audio_format", "mp3"),
        },
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def build_juan(
    cfg: dict, text_id: int, juan: int, api_base: str, out_root: Path,
    key: str | None, no_synth: bool = False,
) -> dict:
    raw = fetch_juan(api_base, text_id, juan)
    if not raw:
        raise RuntimeError(f"text_id={text_id} juan={juan} 无正文")

    segs = split_content(raw)
    pron = to_minimax_dict(text=raw.replace("\n", ""))

    # 两层哈希，各管一件事，理由见 synth_hash_of / content_hash_of 的文档串。
    synth_hash = synth_hash_of(cfg, raw, pron)
    content_hash = content_hash_of(synth_hash, cfg)
    hash8 = content_hash[:8]
    bitrate = cfg.get("bitrate", DEFAULT_BITRATE)
    log(f"[{text_id}/{juan}] {len(raw)} 字 → {len(segs)} 段，词典 {len(pron)} 条，"
        f"synth={synth_hash[:8]} content={hash8} @{bitrate}")

    work = out_root / str(text_id) / f"{juan}-{synth_hash[:8]}.parts"
    work.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    cues: list[dict] = []
    elapsed = 0
    billed = 0
    for i, seg in enumerate(segs):
        part = work / f"{i:04d}.wav"
        if not part.exists():          # 断点续传：重跑不重复付费
            if no_synth:
                # 保险丝。只想换编码却触发了合成，说明 synth_hash 算错了 ——
                # 放任下去会用一份新赌出来的音频顶掉已听审通过的版本。
                raise RuntimeError(
                    f"--no-synth 模式下缺分片 {part}；synth_hash 可能变了，"
                    f"检查 synth_hash_of 的字段是否被改动"
                )
            if not key:
                raise RuntimeError("需要 API key 才能合成；只重编码请加 --no-synth")
            info = synthesize(
                normalize_for_tts(seg.text),
                part,
                voice_id=cfg["voice_id"],
                api_key=key,
                model=cfg.get("model", "speech-2.8-hd"),
                speed=float(cfg.get("speed", 1.0)),
                pronunciation=pron,
                audio_format="wav",
            )
            billed += info.get("usage_characters", 0)
        cues.append({"char_start": seg.char_start, "char_end": seg.char_end,
                     "time_ms": elapsed, "kind": seg.kind})
        elapsed += wav_ms(part)
        parts.append(part)
        if (i + 1) % 20 == 0:
            log(f"  …{i + 1}/{len(segs)} 段，累计 {elapsed / 1000:.0f}s")

    audio_path = out_root / str(text_id) / f"{juan}-{hash8}.mp3"
    concat_to_mp3(parts, audio_path, bitrate)

    meta = {
        "text_id": text_id,
        "juan_num": juan,
        "lang": cfg.get("lang", "zh"),
        "voice_id": cfg["voice_id"],
        "engine": cfg.get("engine", "minimax"),
        "audio_path": f"{text_id}/{juan}-{hash8}.mp3",
        "duration_ms": elapsed,
        "byte_size": audio_path.stat().st_size,
        "audio_format": "mp3",
        "bitrate": bitrate,
        "char_count": len(raw),
        "content_hash": content_hash,
        "synth_hash": synth_hash,
        "cues": cues,
    }
    (out_root / str(text_id) / f"{juan}-{hash8}.cues.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    log(f"  ✓ {audio_path.name}  {elapsed / 60000:.1f} 分钟  "
        f"{meta['byte_size'] / 1e6:.1f} MB  {len(cues)} cue  计费 {billed} 字符")
    return meta


def load_key(key_file: str | None, required: bool = True) -> str | None:
    if key_file:
        for line in Path(key_file).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line:
                return (line.split("=", 1)[1] if "=" in line else line).strip("\"'")
    key = os.environ.get("MINIMAX_API_KEY")
    if not key and required:
        sys.exit("需要 MINIMAX_API_KEY 环境变量，或 --key-file 指向密钥文件")
    return key


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="合成读诵音频")
    ap.add_argument("--manifest", default="scripts/audio/manifest.yml")
    ap.add_argument("--out", default="out/audio")
    ap.add_argument("--api-base", default=DEFAULT_API)
    ap.add_argument("--key-file", help="密钥文件（每行 KEY 或 NAME=KEY）；不给则读环境变量")
    ap.add_argument(
        "--no-synth", action="store_true",
        help="只用已有 WAV 分片重新编码，缺任何一片就报错。换码率时用它 —— "
             "既省掉 API key，也防止哈希算错时静默重新合成顶掉已听审的版本。",
    )
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))
    key = load_key(args.key_file, required=not args.no_synth)
    out_root = Path(args.out)
    done = 0
    for entry in cfg["texts"]:
        for juan in entry["juans"]:
            try:
                build_juan(cfg, entry["text_id"], juan, args.api_base, out_root,
                           key, no_synth=args.no_synth)
                done += 1
            except Exception as exc:
                log(f"✗ text_id={entry['text_id']} juan={juan}: {type(exc).__name__}: {exc}")
    log(f"完成 {done} 卷 → {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
