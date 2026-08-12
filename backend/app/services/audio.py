"""在线读诵音频的读取逻辑。

音频文件本身不经后端 —— 由宿主机 nginx 从静态目录直出（一部经 1~17 MB，
走 FastAPI 是纯浪费）。后端只回「有没有、在哪、什么时候读到哪」。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audio import TextAudio


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
