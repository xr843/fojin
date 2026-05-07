"""Unit tests for ``app.services.attachment_parser``.

We avoid real PDF/DOCX fixtures because their byte format is brittle and
the third-party libs are tested upstream. The tests here lock the
*surface contract* of parse_attachment: extension routing, truncation,
the empty-result placeholder, and CSV/HTML rendering — bugs in *those*
are what's most likely to bleed into the LLM prompt and surprise users.
"""

from __future__ import annotations

import pytest

from app.services.attachment_parser import (
    EMPTY_PLACEHOLDER,
    MAX_PARSED_CHARS,
    TRUNCATION_MARKER,
    parse_attachment,
)


def test_txt_roundtrip():
    text = parse_attachment(b"hello world", "a.txt", "text/plain")
    assert text == "hello world"


def test_md_roundtrip():
    text = parse_attachment(b"# heading\n\nbody", "note.md", "text/markdown")
    assert "heading" in text
    assert "body" in text


def test_unsupported_extension_raises():
    with pytest.raises(ValueError, match="不支持"):
        parse_attachment(b"binary", "evil.exe", "application/octet-stream")


def test_unsupported_no_extension_raises():
    with pytest.raises(ValueError):
        parse_attachment(b"x", "noext", "")


def test_truncation():
    big = ("a" * (MAX_PARSED_CHARS + 100)).encode("utf-8")
    text = parse_attachment(big, "big.txt", "text/plain")
    assert text.endswith(TRUNCATION_MARKER)
    # Truncated to MAX_PARSED_CHARS plus the marker
    assert len(text) == MAX_PARSED_CHARS + len(TRUNCATION_MARKER)


def test_empty_result_returns_placeholder():
    # Whitespace-only input should not raise; placeholder so user knows
    # the parse was attempted.
    text = parse_attachment(b"   \n\n  ", "blank.txt", "text/plain")
    assert text == EMPTY_PLACEHOLDER


def test_csv_renders_pipe_delimited():
    raw = b"name,value\nfoo,1\nbar,2\n"
    text = parse_attachment(raw, "data.csv", "text/csv")
    assert "name | value" in text
    assert "foo | 1" in text
    assert "bar | 2" in text


def test_csv_row_cap():
    rows = ["c1,c2"] + [f"r{i},v{i}" for i in range(500)]
    raw = ("\n".join(rows)).encode("utf-8")
    text = parse_attachment(raw, "many.csv", "text/csv")
    assert "仅显示前" in text


def test_html_strips_tags():
    raw = b"<html><body><h1>Title</h1><p>Body text</p>" \
          b"<script>alert('x')</script></body></html>"
    text = parse_attachment(raw, "page.html", "text/html")
    assert "Title" in text
    assert "Body text" in text
    # Script content should NOT survive — that's the security-relevant
    # invariant.
    assert "alert" not in text


def test_htm_extension_also_works():
    raw = b"<p>hi</p>"
    text = parse_attachment(raw, "page.htm", "text/html")
    assert "hi" in text
