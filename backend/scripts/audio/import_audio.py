"""把 build_audio.py 的产物写进数据库。

幂等：同 (text_id, juan_num, lang, voice_id) 已存在则整条替换（连带 cue），
以便重生成后重导入。

⚠️ **只写数据库**。mp3 文件的上传是另一件事（rsync 到生产静态目录），
   刻意分开 —— 入库可在任意能连库的地方跑，上传只需碰宿主机。

用法::

    cd backend
    python -m scripts.audio.import_audio --dir out/audio           # 入库
    python -m scripts.audio.import_audio --dir out/audio --dry-run # 只看不写
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import delete, select

from app.database import async_session
from app.models.audio import TextAudio, TextAudioCue


async def import_one(meta: dict, dry_run: bool) -> str:
    key = (meta["text_id"], meta["juan_num"], meta["lang"], meta["voice_id"])
    async with async_session() as session:
        existing = (
            await session.execute(
                select(TextAudio).where(
                    TextAudio.text_id == key[0],
                    TextAudio.juan_num == key[1],
                    TextAudio.lang == key[2],
                    TextAudio.voice_id == key[3],
                )
            )
        ).scalar_one_or_none()
        action = "替换" if existing is not None else "新增"
        if dry_run:
            return f"[dry-run] 将{action} text_id={key[0]} juan={key[1]} cue={len(meta['cues'])}"

        if existing is not None:
            await session.execute(
                delete(TextAudioCue).where(TextAudioCue.audio_id == existing.id)
            )
            await session.delete(existing)
            await session.flush()

        audio = TextAudio(
            text_id=meta["text_id"],
            juan_num=meta["juan_num"],
            lang=meta["lang"],
            voice_id=meta["voice_id"],
            engine=meta["engine"],
            audio_path=meta["audio_path"],
            duration_ms=meta["duration_ms"],
            byte_size=meta["byte_size"],
            audio_format=meta["audio_format"],
            char_count=meta["char_count"],
            content_hash=meta["content_hash"],
        )
        session.add(audio)
        await session.flush()
        session.add_all(
            [
                TextAudioCue(
                    audio_id=audio.id,
                    char_start=c["char_start"],
                    char_end=c["char_end"],
                    time_ms=c["time_ms"],
                    kind=c.get("kind", "prose"),
                )
                for c in meta["cues"]
            ]
        )
        await session.commit()
        return f"{action} text_id={key[0]} juan={key[1]} cue={len(meta['cues'])}"


async def run(directory: Path, dry_run: bool) -> int:
    metas = sorted(directory.rglob("*.cues.json"))
    if not metas:
        print(f"{directory} 下没有 *.cues.json —— 先跑 build_audio.py")
        return 1
    for path in metas:
        meta = json.loads(path.read_text(encoding="utf-8"))
        print("✓", await import_one(meta, dry_run))
    print(f"\n共处理 {len(metas)} 卷")
    if not dry_run:
        print("⚠️ 别忘了把 mp3 上传到生产静态目录（rsync），入库只写了元数据")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="音频元数据入库")
    ap.add_argument("--dir", default="out/audio")
    ap.add_argument("--dry-run", action="store_true", help="只显示将做什么，不写库")
    args = ap.parse_args(argv)
    return asyncio.run(run(Path(args.dir), args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
