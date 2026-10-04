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


def _minimal_pdf(pages: list[str]) -> bytes:
    """手工拼一个最小的合法 PDF（标准 Helvetica 字体、xref 偏移精确），
    让解析测试真正跑一遍 pypdf，而不是只测扩展名分派——升级 pypdf 时
    这是唯一能证明「还能读出字」的用例。"""
    objs: list[bytes] = []
    n_pages = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    font_id = 3 + 2 * n_pages
    for i, text in enumerate(pages):
        content_id = 4 + 2 * i
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


def test_pdf_real_parse_extracts_text_per_page():
    text = parse_attachment(_minimal_pdf(["Prajna paramita", "Heart Sutra"]), "x.pdf", "application/pdf")
    assert "Prajna paramita" in text
    assert "Heart Sutra" in text
    assert "\f" in text  # 分页符保留，模型能看出页界


def test_pdf_garbage_raises_value_error():
    with pytest.raises(ValueError):
        parse_attachment(b"%PDF-1.4\nnot really a pdf", "x.pdf", "application/pdf")
