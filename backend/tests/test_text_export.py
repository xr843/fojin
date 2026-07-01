"""Single-text document export tests.

The pure renderers (txt/html/docx/epub) carry all the real logic, so they are
unit-tested directly on an in-memory ExportDoc — no DB needed. The DB assembler
is exercised with an AsyncMock session, following test_apparatus_api.py.
"""

import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.text_export import (
    ExportDoc,
    ExportJuan,
    build_export_doc,
    render,
    render_docx,
    render_epub,
    render_html,
    render_txt,
)


def _doc(**kw) -> ExportDoc:
    return ExportDoc(
        title=kw.get("title", "佛說長阿含經"),
        cbeta_id=kw.get("cbeta_id", "T0001"),
        translator=kw.get("translator", "佛陀耶舍共竺佛念譯"),
        dynasty=kw.get("dynasty", "後秦"),
        juans=kw.get(
            "juans",
            [
                ExportJuan(juan_num=1, lines=["如是我聞。", "一時佛在。"]),
                ExportJuan(juan_num=2, lines=["爾時世尊。"]),
            ],
        ),
    )


# --- TXT ---------------------------------------------------------------------

def test_render_txt_includes_title_metadata_and_all_lines():
    out = render_txt(_doc())
    assert "佛說長阿含經" in out
    assert "佛陀耶舍共竺佛念譯" in out
    assert "如是我聞。" in out
    assert "爾時世尊。" in out
    # both juans are marked
    assert out.count("卷") >= 2


def test_render_txt_omits_missing_metadata():
    out = render_txt(_doc(translator=None, dynasty=None))
    assert "None" not in out


# --- HTML --------------------------------------------------------------------

def test_render_html_is_wellformed_and_escapes():
    doc = _doc(juans=[ExportJuan(juan_num=1, lines=["善男子<惡>&未來。"])])
    out = render_html(doc)
    assert out.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8"' in out
    assert "<title>佛說長阿含經</title>" in out
    # raw angle brackets / ampersand from content must be escaped
    assert "<惡>" not in out
    assert "&lt;惡&gt;" in out
    assert "&amp;" in out


# --- DOCX --------------------------------------------------------------------

def test_render_docx_roundtrips_content():
    from docx import Document

    data = render_docx(_doc())
    assert isinstance(data, bytes) and data[:2] == b"PK"  # zip magic
    parsed = Document(BytesIO(data))
    all_text = "\n".join(p.text for p in parsed.paragraphs)
    assert "佛說長阿含經" in all_text
    assert "如是我聞。" in all_text
    assert "爾時世尊。" in all_text


# --- EPUB --------------------------------------------------------------------

def test_render_epub_is_valid_container():
    data = render_epub(_doc())
    zf = zipfile.ZipFile(BytesIO(data))
    names = zf.namelist()
    # EPUB OCF rule: 'mimetype' must be the first entry and stored uncompressed.
    assert names[0] == "mimetype"
    assert zf.read("mimetype") == b"application/epub+zip"
    info = zf.getinfo("mimetype")
    assert info.compress_type == zipfile.ZIP_STORED
    # required structural files
    assert "META-INF/container.xml" in names
    assert any(n.endswith(".opf") for n in names)
    # content is present and escaped inside a juan document
    juan_docs = [n for n in names if n.endswith(".xhtml")]
    assert juan_docs
    body = "\n".join(zf.read(n).decode("utf-8") for n in juan_docs)
    assert "如是我聞。" in body


def test_render_epub_has_dcterms_modified():
    # EPUB 3 mandates exactly one dcterms:modified in the OPF metadata, else
    # epubcheck fails with RSC-005 and stores reject the file.
    zf = zipfile.ZipFile(BytesIO(render_epub(_doc())))
    opf = next(zf.read(n).decode("utf-8") for n in zf.namelist() if n.endswith(".opf"))
    assert opf.count('property="dcterms:modified"') == 1
    import re

    m = re.search(r'property="dcterms:modified">([^<]+)<', opf)
    assert m and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", m.group(1))


def test_render_epub_escapes_xml():
    doc = _doc(juans=[ExportJuan(juan_num=1, lines=["a<b>&c"])])
    zf = zipfile.ZipFile(BytesIO(render_epub(doc)))
    body = "\n".join(zf.read(n).decode("utf-8") for n in zf.namelist() if n.endswith(".xhtml"))
    assert "<b>" not in body
    assert "&lt;b&gt;" in body and "&amp;c" in body


# --- render() dispatch -------------------------------------------------------

def test_render_dispatch_media_types():
    doc = _doc()
    assert render(doc, "txt")[1].startswith("text/plain")
    assert render(doc, "html")[1].startswith("text/html")
    assert render(doc, "docx")[1] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert render(doc, "epub")[1] == "application/epub+zip"
    # all return bytes payloads
    for fmt in ("txt", "html", "docx", "epub"):
        data, _ = render(doc, fmt)
        assert isinstance(data, bytes) and data


def test_render_rejects_unknown_format():
    with pytest.raises(ValueError):
        render(_doc(), "pdf")


# --- DB assembler ------------------------------------------------------------

def _bt(**kw):
    m = MagicMock()
    m.id = kw.get("id", 1)
    m.title_zh = kw.get("title_zh", "佛說長阿含經")
    m.cbeta_id = kw.get("cbeta_id", "T0001")
    m.translator = kw.get("translator", "佛陀耶舍")
    m.dynasty = kw.get("dynasty", "後秦")
    m.lang = kw.get("lang", "lzh")
    return m


def _content_row(juan_num, content):
    m = MagicMock()
    m.juan_num = juan_num
    m.content = content
    return m


def _assembler_session(bt, rows):
    """First execute() → the BuddhistText scalar; second → content rows."""
    text_result = MagicMock()
    text_result.scalar_one_or_none.return_value = bt
    content_result = MagicMock()
    content_result.scalars.return_value.all.return_value = rows
    session = AsyncMock()
    session.execute.side_effect = [text_result, content_result]
    return session


async def test_build_export_doc_all_juans():
    bt = _bt()
    rows = [_content_row(1, "如是我聞。\n\n一時佛在。"), _content_row(2, "爾時世尊。")]
    doc = await build_export_doc(_assembler_session(bt, rows), text_id=1, juan_num=None)
    assert doc is not None
    assert doc.title == "佛說長阿含經"
    assert doc.cbeta_id == "T0001"
    assert [j.juan_num for j in doc.juans] == [1, 2]
    # blank lines dropped, real lines kept
    assert doc.juans[0].lines == ["如是我聞。", "一時佛在。"]


async def test_build_export_doc_missing_text_returns_none():
    doc = await build_export_doc(_assembler_session(None, []), text_id=999, juan_num=None)
    assert doc is None


# --- endpoint wiring ---------------------------------------------------------

async def test_export_endpoint_sets_download_headers(client):
    from unittest.mock import patch

    with patch("app.api.texts.build_export_doc", AsyncMock(return_value=_doc())):
        resp = await client.get("/api/texts/1/export?format=txt")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert 'filename="T0001.txt"' in resp.headers["content-disposition"]
    assert "如是我聞。" in resp.text


async def test_export_endpoint_single_juan_filename(client):
    from unittest.mock import patch

    with patch("app.api.texts.build_export_doc", AsyncMock(return_value=_doc())):
        resp = await client.get("/api/texts/1/export?format=epub&juan=2")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/epub+zip")
    assert 'filename="T0001_juan2.epub"' in resp.headers["content-disposition"]


async def test_export_endpoint_rejects_bad_format(client):
    resp = await client.get("/api/texts/1/export?format=pdf")
    assert resp.status_code == 400


async def test_export_endpoint_404_when_missing(client):
    from unittest.mock import patch

    with patch("app.api.texts.build_export_doc", AsyncMock(return_value=None)):
        resp = await client.get("/api/texts/999/export?format=txt")
    assert resp.status_code == 404

