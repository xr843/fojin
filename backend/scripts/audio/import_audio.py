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


def audio_key(meta: dict) -> tuple[int, int, str, str]:
    """``text_audio`` 的唯一键 ``(text_id, juan_num, lang, voice_id)``。

    ⚠️ 重复检测与实际入库**必须共用这一个推导**。两边各写一遍，只要默认值
    有一点出入，就会出现「检查放行、入库照撞」——那种 bug 只会在生产上露头。
    """
    return (meta["text_id"], meta["juan_num"], meta["lang"], meta["voice_id"])


async def import_one(meta: dict, dry_run: bool) -> str:
    key = audio_key(meta)
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


def find_duplicate_keys(metas: list[dict]) -> dict[tuple, list[str]]:
    """同一次运行里指向同一把唯一键的产物 —— 返回 {键: [audio_path…]}。

    ``import_one`` 对已存在的行是先删后插，所以重复键意味着**后处理的赢**，
    而顺序由 ``sorted()`` 的字典序决定、与新旧无关。实测形态见
    ``tests/test_audio_import.py`` 的文档串：重编码后新旧两份并存，
    字典序让旧的赢，线上静默回退且日志显示"成功"。
    """
    seen: dict[tuple, list[str]] = {}
    for m in metas:
        seen.setdefault(audio_key(m), []).append(m.get("audio_path", "?"))
    return {k: v for k, v in seen.items() if len(v) > 1}


async def run(directory: Path, dry_run: bool) -> int:
    paths = sorted(directory.rglob("*.cues.json"))
    if not paths:
        print(f"{directory} 下没有 *.cues.json —— 先跑 build_audio.py")
        return 1
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in paths]

    dupes = find_duplicate_keys(metas)
    if dupes:
        print("✗ 同一卷有多份产物，入库会互相顶掉（谁赢取决于文件名字典序，不是新旧）：")
        for (tid, juan, lang, voice), files in dupes.items():
            print(f"   text_id={tid} juan={juan} lang={lang} voice={voice}")
            for f in files:
                print(f"     - {f}")
        print("   删掉过时的 *.mp3 与 *.cues.json 后重跑（.parts 目录留着，重编码要用）")
        return 2

    for meta in metas:
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
