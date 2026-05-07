"""Metadata-direct text retrieval for queries naming a specific 经名+卷号.

When a user types `《楞严经》第一卷` or `楞伽经合辙第7卷指出...`, the right
answer is the actual content of that fascicle, not the top-K nearest
chunks in vector space. Vector retrieval over a 678K-chunk index can
return thematically-similar passages from the wrong text — and the
LLM, having no out-of-band signal that the user named a specific
text, will happily summarise whatever the retrieval served up.

This module short-circuits that case: a query with a recognisable
``《title》第N卷`` pattern triggers a metadata-direct lookup against
``buddhist_texts`` + ``text_contents``. On a confident hit, the returned
``ChatSource`` carries the actual content of that fascicle and the
RAG pipeline skips vector search entirely. On an ambiguous or missing
match, we return ``None`` and let the caller fall back to vector
retrieval — the LLM is more reliable when it has any context than when
it has none.

Design constraints:

- **Conservative trigger**: only fire when the pattern is unambiguous.
  A passing mention like "讲到《心经》怎么样" must not trigger; the user
  has to actually be naming a fascicle.
- **CJK numerals supported**: 第一卷 / 第十二卷 / 第1卷 / 第 12 卷 all
  map to the same int. Mixing arabic + CJK ("第10一卷") is rejected.
- **Trim chunk size**: a juan can be 100K+ characters; we cap the
  ChatSource ``chunk_text`` so the LLM context stays in budget.
"""

import logging
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import BuddhistText, TextContent
from app.schemas.chat import ChatSource

logger = logging.getLogger(__name__)


# Maximum characters of a fascicle's content to inline into the
# ChatSource. 8K characters is roughly two full pages of classical
# Chinese — enough for the LLM to ground a citation, short enough to
# keep the prompt under the 8K-token completion budget set in chat.py.
MAX_FASCICLE_CHUNK_CHARS = 8000

# Conservative trigger: the query must contain 《title》 immediately
# (allowing whitespace) followed by 第<num>卷. Loose mentions of a
# title elsewhere in the sentence don't trigger.
_TITLE_JUAN_RE = re.compile(
    r"《([^》]{1,40})》\s*第\s*([0-9一二三四五六七八九十百]+)\s*卷"
)

# 零 is intentionally excluded — its role in numerals like "一百零三"
# (=103) is a separator, not a digit. Including it would let "一百零"
# parse as 100 and "一百零三" fail to parse as 103. Real fascicle
# numbers expressible only with 零 in the middle (>100, not divisible
# by 10) are rare enough that falling back to vector RAG is acceptable.
_CJK_DIGIT_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}


def _parse_juan_number(raw: str) -> int | None:
    """Convert ``raw`` (digits or CJK numerals) to int.

    Returns ``None`` when the string mixes alphabets or doesn't parse
    cleanly — we'd rather fall back to vector search than guess wrong.
    """
    raw = raw.strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    # Pure CJK form: 一 / 二 / ... 十 / 十一 / ... 二十 / ... 一百二十三
    if any(ch.isdigit() for ch in raw):
        # Mixed: refuse.
        return None
    return _cjk_to_int(raw)


def _cjk_to_int(s: str) -> int | None:
    """Parse 1-3 digit CJK numerals (零, 一-九, 十, 百).

    Sufficient for fascicle numbers — CBETA's largest is 600 卷
    (大般若经). Returns ``None`` on anything not strictly recognised.
    """
    if s == "十":
        return 10
    if s == "百":
        return 100
    # Patterns we accept:
    #   X       → 0-9
    #   十X     → 11-19
    #   X十     → 20, 30, ... 90
    #   X十Y    → 21-99 except *0
    #   百X     → 101-109
    #   X百     → 200, 300, ... 900
    #   X百Y    → e.g. 一百二 = 102
    #   X百Y十Z → e.g. 一百二十三 = 123
    #   X百Y十  → e.g. 一百二十 = 120
    if all(ch in _CJK_DIGIT_MAP for ch in s):
        # All single digits, e.g. "一" or — unlikely — "一二".
        if len(s) == 1:
            return _CJK_DIGIT_MAP[s]
        return None
    n = 0
    if "百" in s:
        head, _, rest = s.partition("百")
        hundreds = _CJK_DIGIT_MAP.get(head) if head else 1
        if hundreds is None:
            return None
        n += hundreds * 100
        s = rest
    if "十" in s:
        head, _, rest = s.partition("十")
        tens = _CJK_DIGIT_MAP.get(head) if head else 1
        if tens is None:
            return None
        n += tens * 10
        s = rest
    if s:
        ones = _CJK_DIGIT_MAP.get(s)
        if ones is None:
            return None
        n += ones
    return n if n > 0 else None


def _detect_title_juan(query: str) -> tuple[str, int] | None:
    """Return (title, juan_num) when the query unambiguously names a
    fascicle, else None. Only the first match is returned; if the user
    names two fascicles in one breath we let vector RAG handle it."""
    m = _TITLE_JUAN_RE.search(query)
    if not m:
        return None
    title = m.group(1).strip()
    if not title:
        return None
    juan = _parse_juan_number(m.group(2))
    if juan is None or juan <= 0:
        return None
    return title, juan


async def try_precise_text_retrieval(
    db: AsyncSession,
    query: str,
    *,
    scope_text_ids: list[int] | None = None,
) -> list[ChatSource] | None:
    """When ``query`` names a specific 《经名》第N卷, return that fascicle's
    content as a single ChatSource. Otherwise return ``None`` so the
    caller falls back to vector retrieval.

    Trades recall for precision: the lookup uses an **exact** match on
    ``buddhist_texts.title_zh``. A loose match (LIKE / fuzzy) would
    reintroduce the very ambiguity vector RAG has — better to return
    None and let semantic search take over than to silently bind the
    user's question to the wrong text.

    ``scope_text_ids`` is the master-mode (法师模式) corpus restriction.
    A precise hit on a text outside the master's allowed corpus must be
    rejected — the persona contract promises that retrieved context
    comes from the master's texts, and a metadata short-circuit that
    silently bypasses that contract is a worse violation than any
    accuracy gain.
    """
    detected = _detect_title_juan(query)
    if detected is None:
        return None
    title, juan_num = detected

    # 1. Resolve the title to a buddhist_texts row. Exact match only;
    #    case is irrelevant for CJK but trim whitespace to be safe.
    text_q = await db.execute(
        select(BuddhistText)
        .where(func.trim(BuddhistText.title_zh) == title)
        .limit(2)
    )
    candidates = list(text_q.scalars())
    if len(candidates) != 1:
        # Zero hits: title not in canon. Multiple hits: ambiguous (some
        # titles legitimately exist in more than one source); let RAG
        # disambiguate via score.
        logger.debug(
            "precise_retrieval miss: title=%r juan=%d candidates=%d",
            title, juan_num, len(candidates),
        )
        return None
    bt = candidates[0]

    if scope_text_ids is not None and bt.id not in scope_text_ids:
        logger.debug(
            "precise_retrieval out-of-scope: text_id=%d title=%r not in master scope",
            bt.id, title,
        )
        return None

    # 2. Resolve the fascicle's content from text_contents. Prefer the
    #    text's primary lang; fall back to any lang if that misses.
    content_q = await db.execute(
        select(TextContent)
        .where(TextContent.text_id == bt.id, TextContent.juan_num == juan_num)
        .order_by(TextContent.lang == bt.lang)
        .limit(1)
    )
    tc = content_q.scalar_one_or_none()
    if tc is None or not tc.content:
        logger.debug(
            "precise_retrieval no content: text_id=%d juan=%d", bt.id, juan_num,
        )
        return None

    chunk_text = tc.content[:MAX_FASCICLE_CHUNK_CHARS]
    truncated = len(tc.content) > MAX_FASCICLE_CHUNK_CHARS
    if truncated:
        # Mark the truncation so the LLM doesn't claim coverage of the
        # tail it never saw.
        chunk_text += "\n…（本卷剩余内容因长度限制未列入此次检索；引用时请说明）"

    return [
        ChatSource(
            text_id=bt.id,
            juan_num=juan_num,
            chunk_index=0,
            chunk_text=chunk_text,
            score=1.0,
            title_zh=bt.title_zh or "",
            lang=tc.lang or bt.lang or "lzh",
            source_id=bt.source_id,
        )
    ]
