from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Gaiji(Base):
    """CBETA-style rare-character (缺字/gaiji) entries.

    A gaiji is a Chinese character that lacks a standard Unicode code point
    at the time the source text was digitized. CBETA encodes these as
    composition expressions like "[木*奈]" (tree radical combined with 奈).
    To keep search recall correct across passages containing gaiji, we
    normalize on both index and query paths: composition / PUA / Big5
    variants all collapse to norm_unicode_char when present, otherwise
    the composition string is retained verbatim.

    Upstream: github.com/cbeta-org/cbeta_gaiji (XML/JSON/CSV releases).
    """

    __tablename__ = "gaiji"
    __table_args__ = (
        # Speed up the search-side normalization scan: query text is
        # decomposed into tokens, each looked up by composition or pua.
        Index("ix_gaiji_norm_unicode_char", "norm_unicode_char"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # CBETA stable identifier, e.g. "CB00001". Unique across the corpus.
    cb_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    # Composition expression as used inline in CBETA texts, e.g. "[木*奈]".
    # Indexed because the search-time normalizer scans incoming queries
    # for these literal patterns.
    composition: Mapped[str | None] = mapped_column(String(200), index=True)
    # The glyph itself if a real Unicode codepoint was eventually assigned.
    # NULL when the character is still gaiji-only.
    unicode_char: Mapped[str | None] = mapped_column(String(8))
    unicode_codepoint: Mapped[str | None] = mapped_column(String(20))  # "U+2A6B2"
    # The normalized Unicode the *search index* should fold this gaiji to.
    # Often identical to unicode_char; differs when the gaiji has a
    # commonly-used variant character (e.g. CBETA assigns norm_unicode
    # to the simplified or BMP-range fallback for retrieval purposes).
    norm_unicode_char: Mapped[str | None] = mapped_column(String(8))
    norm_big5_char: Mapped[str | None] = mapped_column(String(8))
    # CBETA Private Use Area assignment, "U+F0000" + numeric ID.
    # Some older corpus files still encode gaiji this way.
    pua_codepoint: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    # Optional CBETA-hosted glyph image used as last-resort fallback in UI
    # when no Unicode form is available.
    image_url: Mapped[str | None] = mapped_column(String(500))
    # Reference to the MoE 異體字字典 variant_id when CBETA links one.
    # Empirically up to 60 chars (comma-joined multi-IDs); widened in 0151.
    moe_variant_id: Mapped[str | None] = mapped_column(String(100))
    # Provenance — which upstream produced this row, frozen at ingest time
    # so re-imports can detect upstream changes via cb_code + upstream_version.
    source: Mapped[str] = mapped_column(String(20), server_default="cbeta", nullable=False)
    upstream_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
