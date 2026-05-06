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

from fastapi import APIRouter, Depends, HTTPException, Response
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chat import SharedQA

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
