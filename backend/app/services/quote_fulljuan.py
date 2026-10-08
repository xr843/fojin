"""整卷兜底：引文在检索片段里找不到时，到所引那一卷的全文里再核一次。

quote_verifier 是闭世界的——只拿检索回来的几个 ~500 字片段做子串比对。模型
凭记忆引对了经文、而那一段恰好没被召回时，一句一字不差的引文也会被降级成叙述，
用户看到的是「这段没核实」。生产回放（2026-07-10 至 10-07，单段、非省略号的降级
引文）：63 条逐字在所引那一卷里——是误降。

兜底只放宽「在哪找」，不放宽「怎么算对」：
- 仍是归一化后的逐字子串（节引则各段按序、且首尾跨度不超过 ``MAX_ELIDED_SPAN``）；
- 只查被引书名**确实被检索到**的那几部（text_id 取自检索片段，不按书名查库），
  且只查答案写明的那一卷——卷号写错的引文不在这里救；
- 读库失败一律当作没有兜底，绝不因此打断回答。

全文按字归一化（passage_locator.fast_normalise）：整卷几万字跑 OpenCC 要几百毫秒，
按字查表只是 str.translate。代价是丢掉 OpenCC 极少数的词组级转换——只会让个别
引文找不到，不会让错的变对。
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import TextContent
from app.schemas.chat import ChatSource
from app.services.passage_locator import fast_normalise
from app.services.quote_verifier import FullJuanCheck, _elided_segments

logger = logging.getLogger(__name__)

# 一个回答最多读几卷。生产里一个回答的失败引文通常落在 1–2 卷；上限只防病态答案。
MAX_FULL_JUANS = 6

# 整卷里节引各段按序出现还不够——几万字里四字短段随处可见。要求首段起点到末段
# 终点不超过这个跨度：生产真节引首尾跨度中位 68 字、97% 在 450 字内（见 #1277）。
MAX_ELIDED_SPAN = 600


def _in_order_within(segments: list[str], haystack: str, max_span: int) -> bool:
    """Segments appear in order, first-start to last-end within ``max_span``."""
    start = haystack.find(segments[0])
    while start >= 0:
        pos = start + len(segments[0])
        for seg in segments[1:]:
            i = haystack.find(seg, pos)
            if i < 0 or i + len(seg) - start > max_span:
                break
            pos = i + len(seg)
        else:
            return True
        start = haystack.find(segments[0], start + 1)
    return False


def make_full_juan_check(bodies: dict[tuple[int, int], str]) -> FullJuanCheck:
    """Build the verifier's fallback over already-normalised fascicle bodies."""

    def check(quote: str, candidates: list[ChatSource], juan: int) -> bool:
        texts = [bodies.get((tid, juan)) for tid in dict.fromkeys(c.text_id for c in candidates)]
        texts = [t for t in texts if t]
        if not texts:
            return False
        needle = fast_normalise(quote)
        if needle and any(needle in t for t in texts):
            return True
        segments = _elided_segments(quote, fast_normalise)
        return segments is not None and any(_in_order_within(segments, t, MAX_ELIDED_SPAN) for t in texts)

    return check


async def load_full_juan_check(db: AsyncSession, keys: list[tuple[int, int]]) -> FullJuanCheck | None:
    """Load the fascicles named by ``juans_to_recheck`` and return the fallback
    check — or None when there is nothing to recheck or the read fails (the
    verifier then behaves exactly as before). Callers compute ``keys`` first so
    the ~all answers with nothing to recheck never open a session."""
    keys = keys[:MAX_FULL_JUANS]
    if not keys:
        return None
    t0 = time.monotonic()
    try:
        rows = (
            await db.execute(
                select(TextContent.text_id, TextContent.juan_num, TextContent.content).where(
                    tuple_(TextContent.text_id, TextContent.juan_num).in_(keys),
                    TextContent.lang == "lzh",
                )
            )
        ).all()
    except Exception:
        logger.warning("quote full-juan fallback: load failed for %s", keys, exc_info=True)
        return None
    bodies = {(tid, juan): fast_normalise(content) for tid, juan, content in rows if content}
    logger.info(
        "quote full-juan fallback: %d/%d juans loaded in %.0f ms",
        len(bodies), len(keys), (time.monotonic() - t0) * 1000,
    )
    return make_full_juan_check(bodies) if bodies else None
