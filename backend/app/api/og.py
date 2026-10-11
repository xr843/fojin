"""Dynamic Open Graph card images for shareable Q&A links.

Public Q&A links (``/share/qa/{share_id}``) used to inherit the homepage
``og:image`` — a generic landscape photo — so every link shared on
linux.do, X, WeChat, Telegram, etc. looked identical and carried no
information about the actual question. This module renders a per-link
1200×630 PNG containing the question text plus a ``佛津 FoJin`` mark, so
crawler previews actually identify the content.

Implementation notes:
- Pure Pillow, no headless browser. Generation budget: well under 200ms
  on a single CPU core for our card layout.
- The CJK font is loaded once at import and reused. ``fonts-noto-cjk``
  is installed in the backend image; we fall back to PIL's default
  bitmap font if the file is missing so missing fonts never crash the
  endpoint (the rendered card just degrades to plain ASCII).
- Responses are cached at the CDN edge for 24h via ``Cache-Control``.
  A change to the underlying SharedQA row will only become visible after
  the cache expires; that is acceptable because shared cards are
  immutable by design.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from opencc import OpenCC
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.elasticsearch import get_es
from app.database import get_db
from app.models.chat import SharedQA
from app.schemas.verification import ClaimVerdict
from app.services.claim_check import check_claim
from app.services.quote_lookup import QuoteTooShortError, SearchUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/og", tags=["og"])

# Card dimensions chosen to satisfy both Twitter ``summary_large_image``
# and Facebook/LinkedIn recommended sizes.
CARD_WIDTH = 1200
CARD_HEIGHT = 630
PADDING = 64

# Font candidates tried in order. The first existing path wins; we
# resolve once at import time so the first request isn't penalized.
_FONT_CANDIDATES = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
)


def _resolve_font_path() -> Path | None:
    for candidate in _FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


_FONT_PATH = _resolve_font_path()
if _FONT_PATH is None:
    logger.warning(
        "No CJK font found; OG card text will fall back to PIL default. Install fonts-noto-cjk in the runtime image."
    )


def _font(size: int) -> ImageFont.ImageFont:
    """Return a font of the given size, or PIL's default if no TTF is available."""
    if _FONT_PATH is None:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(str(_FONT_PATH), size)
    except OSError:
        # The file existed at startup but failed at load (corruption,
        # permissions, etc.) — never let this break a card render.
        return ImageFont.load_default()


# Pre-load the font sizes we use so each request is one ImageDraw call.
_TITLE_FONT = _font(64)
_HEADER_FONT = _font(28)
_FOOTER_FONT = _font(24)
_WATERMARK_FONT = _font(22)


def _wrap_question(question: str, *, max_chars_per_line: int = 16, max_lines: int = 4) -> list[str]:
    """Wrap a CJK question into at most ``max_lines`` lines.

    ``textwrap.wrap`` doesn't understand that CJK characters take ~1
    visual cell each with no inter-word breaks, so we hand-wrap by
    character count. The truncated tail gets an ellipsis.
    """
    cleaned = " ".join(question.split())
    if not cleaned:
        return [""]

    # Wrap: drop lines beyond max_lines, ellipsis on the last surviving
    # line if there's overflow.
    lines: list[str] = []
    cursor = 0
    while cursor < len(cleaned) and len(lines) < max_lines:
        chunk = cleaned[cursor : cursor + max_chars_per_line]
        lines.append(chunk)
        cursor += max_chars_per_line

    if cursor < len(cleaned) and lines:
        lines[-1] = lines[-1].rstrip()[: max_chars_per_line - 1] + "…"
    return lines


def _extract_first_source_label(sources) -> str | None:
    """Pull a short citation label out of the saved sources JSON, if any."""
    if not sources or not isinstance(sources, list):
        return None
    first = sources[0]
    if not isinstance(first, dict):
        return None
    # Prefer the displayable Chinese title; fall back to whatever's available.
    for key in ("title_zh", "title", "name", "cbeta_id"):
        value = first.get(key)
        if value:
            return str(value)[:40]
    return None


def _render_qa_card(question: str, source_label: str | None) -> bytes:
    """Render the 1200×630 PNG card for a Q&A question."""
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(252, 250, 246))
    draw = ImageDraw.Draw(img)

    # Subtle top accent bar to break up the empty white.
    draw.rectangle(
        ((0, 0), (CARD_WIDTH, 6)),
        fill=(143, 100, 65),  # warm 佛津 brown-gold
    )

    # Header: site identity.
    draw.text(
        (PADDING, PADDING),
        "佛津 FoJin · AI 佛学问答",
        fill=(143, 100, 65),
        font=_HEADER_FONT,
    )

    # Main: question lines, vertically centered around the card middle.
    lines = _wrap_question(question)
    line_height = 84
    block_height = line_height * len(lines)
    start_y = max(PADDING + 60, (CARD_HEIGHT - block_height) // 2)
    for i, line in enumerate(lines):
        draw.text(
            (PADDING, start_y + i * line_height),
            line,
            fill=(34, 32, 30),
            font=_TITLE_FONT,
        )

    # Footer: cited sutra label (if any).
    footer_y = CARD_HEIGHT - PADDING - 28
    if source_label:
        draw.text(
            (PADDING, footer_y),
            f"引用 · {source_label}",
            fill=(110, 92, 78),
            font=_FOOTER_FONT,
        )

    # Watermark, bottom-right.
    watermark = "fojin.app"
    bbox = draw.textbbox((0, 0), watermark, font=_WATERMARK_FONT)
    wm_width = bbox[2] - bbox[0]
    draw.text(
        (CARD_WIDTH - PADDING - wm_width, CARD_HEIGHT - PADDING - 22),
        watermark,
        fill=(140, 130, 120),
        font=_WATERMARK_FONT,
    )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@router.get("/share/qa/{share_id}")
async def shared_qa_og_image(
    share_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return a 1200×630 PNG card for a shared Q&A.

    Uses the question text plus the first cited sutra as the only
    visible content. If the share id does not exist, returns 404.
    """
    record = await db.scalar(select(SharedQA).where(SharedQA.id == share_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Shared Q&A not found")

    source_label = _extract_first_source_label(record.sources)
    png = _render_qa_card(record.question, source_label)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── 「这句经，佛真的说过吗？」 result card (GET /api/og/verify?q=…) ───────────
#
# Shown as an <img> on /verify (long-press to save in WeChat) and used as the
# page's og:image. Only ``q`` (and the label language) is accepted: the verdict
# is always recomputed by check_claim, so no URL can make this card say
# something fojin did not find.

_VERDICT_COLOURS = {
    "sutra": (46, 125, 82),
    "not_sutra": (176, 122, 33),
    "variant": (47, 111, 143),
    "partial": (196, 98, 45),
    "absent": (120, 115, 108),
}
_FOUND_INK = (34, 32, 30)
_MISSING_INK = (176, 168, 158)

_CLASS_LABELS = {
    "zh": {
        "vinaya": "律典", "treatise": "论典（菩萨、论师所造）", "commentary": "注疏",
        "school": "宗派与祖师著作", "history": "史传", "apocrypha": "疑伪经",
        "later": "后世注疏、语录", "unknown": "其他典籍",
    },
    "zh-Hant": {
        "vinaya": "律典", "treatise": "論典（菩薩、論師所造）", "commentary": "注疏",
        "school": "宗派與祖師著作", "history": "史傳", "apocrypha": "疑偽經",
        "later": "後世注疏、語錄", "unknown": "其他典籍",
    },
    "en": {
        "vinaya": "a Vinaya text", "treatise": "a treatise (śāstra)", "commentary": "a commentary",
        "school": "a school or master's work", "history": "a historical work", "apocrypha": "an apocryphal sūtra",
        "later": "a later commentary or record", "unknown": "another work",
    },
}
_COPY = {
    "zh": {
        "header": "佛津 FoJin · 这句经，佛真的说过吗？",
        "sutra": "出自佛经",
        "not_sutra": "出自{cls}，不是佛经",
        "variant": "经中有此句，用字略有不同",
        "partial": "只有部分能在大藏经中找到",
        "absent": "大藏经中未见",
        "canon_reads": "经中原文：{text}",
        "source": "出处 · {titles}",
        "missing": "灰色部分：大藏经中未见",
        "footer": "逐字比对 CBETA 原文 · fojin.app/verify",
    },
    "zh-Hant": {
        "header": "佛津 FoJin · 這句經，佛真的說過嗎？",
        "sutra": "出自佛經",
        "not_sutra": "出自{cls}，不是佛經",
        "variant": "經中有此句，用字略有不同",
        "partial": "只有部分能在大藏經中找到",
        "absent": "大藏經中未見",
        "canon_reads": "經中原文：{text}",
        "source": "出處 · {titles}",
        "missing": "灰色部分：大藏經中未見",
        "footer": "逐字比對 CBETA 原文 · fojin.app/verify",
    },
    "en": {
        "header": "FoJin · Did the Buddha really say this?",
        "sutra": "Found in a sūtra",
        "not_sutra": "Found in {cls}, not a sūtra",
        "variant": "In the canon, worded slightly differently",
        "partial": "Only partly found in the canon",
        "absent": "Not found in the Buddhist canon",
        "canon_reads": "The canon reads: {text}",
        "source": "Source · {titles}",
        "missing": "Grey: not found in the canon",
        "footer": "Checked word for word against CBETA · fojin.app/verify",
    },
}
_T2S = OpenCC("t2s")
_BADGE_FONT = _font(40)
_QUOTE_FONT = _font(48)
_QUOTE_MAX_LINES = 4


def _layout_segments(verdict: ClaimVerdict, max_width: int) -> list[list[tuple[str, tuple[int, int, int]]]]:
    """Wrap the pasted text char by char into ≤4 lines, colouring each clause."""
    # Near misses are in the canon (worded slightly differently) — not greyed.
    runs = [(seg.text, _FOUND_INK if (seg.found or seg.close) else _MISSING_INK) for seg in verdict.segments]
    if len(runs) > 1:  # clause texts dropped their punctuation when split
        runs = [(t + ("，" if i < len(runs) - 1 else ""), c) for i, (t, c) in enumerate(runs)]
    lines: list[list[tuple[str, tuple[int, int, int]]]] = [[]]
    width = 0.0
    for text, colour in runs:
        for ch in text:
            w = _QUOTE_FONT.getlength(ch) if hasattr(_QUOTE_FONT, "getlength") else 24
            if width + w > max_width:
                if len(lines) == _QUOTE_MAX_LINES:
                    last = lines[-1]
                    last[-1] = (last[-1][0][:-1] + "…", last[-1][1]) if last and last[-1][0] else last[-1]
                    return lines
                lines.append([])
                width = 0.0
            if lines[-1] and lines[-1][-1][1] == colour:
                lines[-1][-1] = (lines[-1][-1][0] + ch, colour)
            else:
                lines[-1].append((ch, colour))
            width += w
    return lines


def _render_verify_card(verdict: ClaimVerdict, lang: str) -> bytes:
    copy = _COPY[lang]
    accent = _VERDICT_COLOURS[verdict.verdict]
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(252, 250, 246))
    draw = ImageDraw.Draw(img)
    draw.rectangle(((0, 0), (CARD_WIDTH, 10)), fill=accent)
    draw.text((PADDING, PADDING - 8), copy["header"], fill=(143, 100, 65), font=_HEADER_FONT)

    if verdict.verdict == "not_sutra":
        cls = _CLASS_LABELS[lang].get(verdict.source_class or "unknown", _CLASS_LABELS[lang]["unknown"])
        badge = copy["not_sutra"].format(cls=cls)
    else:
        badge = copy[verdict.verdict]
    bx, by = PADDING, PADDING + 48
    bbox = draw.textbbox((bx + 24, by + 12), badge, font=_BADGE_FONT)
    draw.rounded_rectangle(((bx, by), (bbox[2] + 24, bbox[3] + 14)), radius=14, fill=accent)
    draw.text((bx + 24, by + 12), badge, fill=(255, 255, 255), font=_BADGE_FONT)

    y = by + 112
    for line in _layout_segments(verdict, CARD_WIDTH - 2 * PADDING):
        x = PADDING
        for text, colour in line:
            draw.text((x, y), text, fill=colour, font=_QUOTE_FONT)
            x += draw.textlength(text, font=_QUOTE_FONT)
        y += 66

    if verdict.verdict == "variant":
        close = next((seg.close for seg in verdict.segments if seg.close is not None), None)
        if close is not None:
            # window_normalised is in the matcher's normalised space (simplified,
            # punctuation stripped) — shown as-is; the page links the source.
            line = copy["canon_reads"].format(text=close.window_normalised)
            draw.text((PADDING, y + 6), line[:34] + ("…" if len(line) > 34 else ""), fill=(47, 111, 143), font=_FOOTER_FONT)

    titles: list[str] = []
    for seg in verdict.segments:
        refs = list(seg.sources) + ([seg.close] if seg.close is not None else [])
        for src in refs:
            title = src.title_zh or src.cbeta_id or ""
            if lang == "zh":  # titles are stored in traditional script (CBETA)
                title = _T2S.convert(title)
            if title and f"《{title}》" not in titles:
                titles.append(f"《{title}》")
    footer_y = CARD_HEIGHT - PADDING - 30
    if titles:
        label = copy["source"].format(titles="".join(titles[:2]) + ("…" if len(titles) > 2 else ""))
        draw.text((PADDING, footer_y - 44), label[:60], fill=(110, 92, 78), font=_FOOTER_FONT)
    if verdict.verdict == "partial":
        draw.text((PADDING, footer_y), copy["missing"], fill=_MISSING_INK, font=_WATERMARK_FONT)
    fb = draw.textbbox((0, 0), copy["footer"], font=_WATERMARK_FONT)
    draw.text((CARD_WIDTH - PADDING - (fb[2] - fb[0]), footer_y + 4), copy["footer"], fill=(140, 130, 120), font=_WATERMARK_FONT)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@router.get("/verify")
async def verify_card_image(
    q: str = Query(..., min_length=1, max_length=200),
    lang: str = Query("zh", pattern="^(zh|zh-Hant|en)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """1200×630 PNG of the /verify result for ``q``, verdict recomputed server-side."""
    try:
        verdict = await check_claim(db, get_es(), q)
    except QuoteTooShortError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SearchUnavailableError as exc:
        # Never draw a branded「大藏经中未见」card for a search that failed.
        raise HTTPException(status_code=503, detail="search temporarily unavailable") from exc
    return Response(
        content=_render_verify_card(verdict, lang),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )

