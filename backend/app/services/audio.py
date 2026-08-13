"""在线读诵音频的读取逻辑。

音频文件本身不经后端 —— 由宿主机 nginx 从静态目录直出（一部经 1~17 MB，
走 FastAPI 是纯浪费）。后端只回「有没有、在哪、什么时候读到哪」。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audio import TextAudio
from app.models.text import BuddhistText


def build_audio_payload(audio: TextAudio) -> dict:
    """ORM 行 → API 响应字典。

    cues 按 time_ms 升序 —— 前端 findCueIndex 是二分查找，乱序会让高亮跳位。
    """
    cues = sorted(audio.cues, key=lambda c: c.time_ms)
    return {
        "url": f"/audio/{audio.audio_path}",
        "voice_id": audio.voice_id,
        "engine": audio.engine,
        "duration_ms": audio.duration_ms,
        "cues": [
            {
                "char_start": c.char_start,
                "char_end": c.char_end,
                "time_ms": c.time_ms,
                "kind": c.kind,
            }
            for c in cues
        ],
    }


async def get_juan_audio(
    session: AsyncSession, text_id: int, juan_num: int, lang: str = "zh"
) -> dict | None:
    """取某一卷的音频。同卷多音色时取最新创建的一条。"""
    stmt = (
        select(TextAudio)
        .where(
            TextAudio.text_id == text_id,
            TextAudio.juan_num == juan_num,
            TextAudio.lang == lang,
        )
        .options(selectinload(TextAudio.cues))
        .order_by(TextAudio.created_at.desc())
        .limit(1)
    )
    audio = (await session.execute(stmt)).scalar_one_or_none()
    return build_audio_payload(audio) if audio else None


def group_audio_by_text(rows: list[tuple]) -> list[dict]:
    """``[(TextAudio, BuddhistText), …]`` → 按经聚合的目录项。

    音频按**卷**存，索引页按**经**列 —— 使用者找的是「哪部经能听」。
    排序用总时长升序而非 text_id：短经先上是这个功能的现实
    （心經 1.7 分钟 vs 壇經一卷 134 分钟），让人一眼看到能听完的那几部。
    """
    by_text: dict[int, dict] = {}
    for audio, text in rows:
        item = by_text.setdefault(
            audio.text_id,
            {
                "text_id": audio.text_id,
                "title_zh": text.title_zh,
                "translator": text.translator,
                "dynasty": text.dynasty,
                "taisho_id": text.taisho_id,
                "engine": audio.engine,
                "juans": [],
            },
        )
        item["juans"].append(
            {
                "juan_num": audio.juan_num,
                "duration_ms": audio.duration_ms,
                "url": f"/audio/{audio.audio_path}",
            }
        )

    items = []
    for item in by_text.values():
        item["juans"].sort(key=lambda j: j["juan_num"])
        item["juan_count"] = len(item["juans"])
        item["total_duration_ms"] = sum(j["duration_ms"] for j in item["juans"])
        items.append(item)
    items.sort(key=lambda it: (it["total_duration_ms"], it["text_id"]))
    return items


async def list_available_audio(session: AsyncSession, lang: str = "zh") -> list[dict]:
    """有读诵音频的经的完整目录。

    音频总量按设计就很小（第一期一部，扩到十部也不过十行），所以不分页 ——
    前端一次取回，索引页与经典详情页共用同一份缓存。
    """
    stmt = (
        select(TextAudio, BuddhistText)
        .join(BuddhistText, BuddhistText.id == TextAudio.text_id)
        .where(TextAudio.lang == lang)
        .order_by(TextAudio.text_id, TextAudio.juan_num)
    )
    return group_audio_by_text(list((await session.execute(stmt)).all()))
