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


def log(*a: object) -> None:
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def fetch_juan(api_base: str, text_id: int, juan: int) -> str:
    req = urllib.request.Request(f"{api_base}/texts/{text_id}/juans/{juan}", headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("content") or ""


def wav_ms(path: Path) -> int:
    with contextlib.closing(wave.open(str(path))) as w:
        return int(w.getnframes() / w.getframerate() * 1000)


def concat_to_mp3(parts: list[Path], out_path: Path) -> None:
    """WAV 分片无损拼接后一次性编码为 MP3。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        for p in parts:
            fh.write(f"file '{p.resolve()}'\n")
        lst = fh.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
             "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "32000", "-ac", "1", str(out_path)],
            check=True, capture_output=True,
        )
    finally:
        Path(lst).unlink(missing_ok=True)


def build_juan(cfg: dict, text_id: int, juan: int, api_base: str, out_root: Path, key: str) -> dict:
    raw = fetch_juan(api_base, text_id, juan)
    if not raw:
        raise RuntimeError(f"text_id={text_id} juan={juan} 无正文")

    content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    hash8 = content_hash[:8]
    segs = split_content(raw)
    pron = to_minimax_dict(text=raw.replace("\n", ""))
    log(f"[{text_id}/{juan}] {len(raw)} 字 → {len(segs)} 段，词典 {len(pron)} 条，hash={hash8}")

    work = out_root / str(text_id) / f"{juan}-{hash8}.parts"
    work.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    cues: list[dict] = []
    elapsed = 0
    billed = 0
    for i, seg in enumerate(segs):
        part = work / f"{i:04d}.wav"
        if not part.exists():          # 断点续传：重跑不重复付费
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
    concat_to_mp3(parts, audio_path)

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
        "char_count": len(raw),
        "content_hash": content_hash,
        "cues": cues,
    }
    (out_root / str(text_id) / f"{juan}-{hash8}.cues.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    log(f"  ✓ {audio_path.name}  {elapsed / 60000:.1f} 分钟  "
        f"{meta['byte_size'] / 1e6:.1f} MB  {len(cues)} cue  计费 {billed} 字符")
    return meta


def load_key(key_file: str | None) -> str:
    if key_file:
        for line in Path(key_file).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line:
                return (line.split("=", 1)[1] if "=" in line else line).strip("\"'")
    key = os.environ.get("MINIMAX_API_KEY")
    if not key:
        sys.exit("需要 MINIMAX_API_KEY 环境变量，或 --key-file 指向密钥文件")
    return key


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="合成读诵音频")
    ap.add_argument("--manifest", default="scripts/audio/manifest.yml")
    ap.add_argument("--out", default="out/audio")
    ap.add_argument("--api-base", default=DEFAULT_API)
    ap.add_argument("--key-file", help="密钥文件（每行 KEY 或 NAME=KEY）；不给则读环境变量")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))
    key = load_key(args.key_file)
    out_root = Path(args.out)
    done = 0
    for entry in cfg["texts"]:
        for juan in entry["juans"]:
            try:
                build_juan(cfg, entry["text_id"], juan, args.api_base, out_root, key)
                done += 1
            except Exception as exc:
                log(f"✗ text_id={entry['text_id']} juan={juan}: {type(exc).__name__}: {exc}")
    log(f"完成 {done} 卷 → {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
