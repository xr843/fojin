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
from app.services.text_reflow import reflow


def _juan(juan_num: int, lines: list[str]) -> ExportJuan:
    """Build a juan the way build_export_doc does: raw lines + reflow segments."""
    raw = "\n".join(lines)
    return ExportJuan(juan_num=juan_num, lines=lines, segments=reflow(raw))


def _doc(**kw) -> ExportDoc:
    return ExportDoc(
        title=kw.get("title", "佛說長阿含經"),
        cbeta_id=kw.get("cbeta_id", "T0001"),
        translator=kw.get("translator", "佛陀耶舍共竺佛念譯"),
        dynasty=kw.get("dynasty", "後秦"),
        juans=kw.get(
            "juans",
            [
                _juan(1, ["爾時世尊，處於此座，成最正覺。", "智入三世，悉皆平等。"]),
                _juan(2, ["其身充滿一切世間，其音普順十方國土。"]),
            ],
        ),
    )


# --- TXT ---------------------------------------------------------------------

def test_render_txt_includes_title_metadata_and_all_lines():
    out = render_txt(_doc())
    assert "佛說長阿含經" in out
    assert "佛陀耶舍共竺佛念譯" in out
    assert "爾時世尊，處於此座，成最正覺。" in out
    assert "其身充滿一切世間，其音普順十方國土。" in out
    # both juans are marked
    assert out.count("卷") >= 2


def test_render_txt_omits_missing_metadata():
    out = render_txt(_doc(translator=None, dynasty=None))
    assert "None" not in out


# --- HTML --------------------------------------------------------------------

def test_render_html_is_wellformed_and_escapes():
    doc = _doc(juans=[_juan(1, ["善男子，<惡>&未來，皆悉明見。"])])
    out = render_html(doc)
    assert out.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8"' in out
    assert "<title>佛說長阿含經</title>" in out
    # raw angle brackets / ampersand from content must be escaped
    assert "<惡>" not in out
    assert "&lt;惡&gt;" in out
    assert "&amp;" in out


def test_render_html_uses_web_layout_classes():
    # HTML must carry the reader.css-matching segment classes, not bare <p>.
    doc = _doc(juans=[_juan(1, ["諸一切種諸冥滅，", "拔眾生出生死泥，"])])
    out = render_html(doc)
    assert 'class="verse"' in out          # opening equal-clause lines → verse
    assert 'class="juan"' in out           # juan heading
    assert ".prose{text-indent:2em" in out  # prose paragraph style present


# --- DOCX --------------------------------------------------------------------

def test_render_docx_roundtrips_content():
    from docx import Document

    data = render_docx(_doc())
    assert isinstance(data, bytes) and data[:2] == b"PK"  # zip magic
    parsed = Document(BytesIO(data))
    all_text = "\n".join(p.text for p in parsed.paragraphs)
    assert "佛說長阿含經" in all_text
    assert "爾時世尊，處於此座，成最正覺。" in all_text
    assert "其身充滿一切世間，其音普順十方國土。" in all_text


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
    assert "爾時世尊，處於此座，成最正覺。" in body


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
    doc = _doc(juans=[_juan(1, ["善哉，a<b>&c，如是我說。"])])
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
    m.source_id = kw.get("source_id")
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
    assert "爾時世尊，處於此座，成最正覺。" in resp.text


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



# --- attribution / 版權說明 ----------------------------------------------------
# CBETA's copyright page makes "附上本說明及版本資訊" a condition of redistribution,
# and CC BY-NC-SA 3.0 requires the licence URI on every copy. Non-CBETA texts
# used to be labelled "CBETA …" in every format.

from app.services.text_export import (
    CBETA_LICENSE_URL,
    CBETA_STATEMENT,
    CBETA_VERSION,
    ExportSource,
)

_REDISTRIBUTION_CLAUSE = "需於成品附上本說明及版本資訊"

_SRC_84000 = ExportSource(
    code="84000",
    name_zh="84000 藏传佛典翻译",
    name_en="84000: Translating the Words of the Buddha",
    base_url="https://read.84000.co",
    license_spdx="CC-BY-NC-ND-4.0",
    license_url="https://creativecommons.org/licenses/by-nc-nd/4.0/",
)
_SRC_GRETIL = ExportSource(code="gretil", name_zh="GRETIL 梵文文献库", name_en="GRETIL")


def _epub_files(doc) -> dict[str, str]:
    with zipfile.ZipFile(BytesIO(render_epub(doc))) as zf:
        return {n: zf.read(n).decode("utf-8") for n in zf.namelist()}


def _docx_text(doc) -> str:
    from docx import Document

    return "\n".join(p.text for p in Document(BytesIO(render_docx(doc))).paragraphs)


@pytest.mark.parametrize("fmt", ["txt", "html", "docx", "epub"])
def test_cbeta_export_carries_statement_version_and_licence(fmt):
    doc = _doc()
    doc.text_id = 42
    if fmt == "epub":
        text = "\n".join(_epub_files(doc).values())
    elif fmt == "docx":
        text = _docx_text(doc)
    else:
        text = render(doc, fmt)[0].decode("utf-8")
    assert _REDISTRIBUTION_CLAUSE in text
    for line in CBETA_STATEMENT:
        assert line in text
    assert CBETA_VERSION in text
    assert CBETA_LICENSE_URL in text
    assert "https://fojin.app/texts/42" in text


def test_epub_colophon_is_in_spine_nav_and_rights_metadata():
    files = _epub_files(_doc())
    assert "OEBPS/colophon.xhtml" in files
    opf = files["OEBPS/content.opf"]
    assert '<itemref idref="colophon"/>' in opf
    assert "<dc:rights>" in opf and "3.0" in opf and CBETA_LICENSE_URL in opf
    assert "<dc:publisher>" in opf
    assert 'href="colophon.xhtml"' in files["OEBPS/nav.xhtml"]
    # still well-formed XML everywhere
    import xml.dom.minidom

    for name, body in files.items():
        if name.endswith((".xhtml", ".opf", ".xml")):
            xml.dom.minidom.parseString(body.encode("utf-8"))


@pytest.mark.parametrize("fmt", ["txt", "html", "docx", "epub"])
def test_non_cbeta_text_is_not_labelled_cbeta(fmt):
    doc = _doc(cbeta_id="84K-toh1", title="Toh 1")
    doc.source = _SRC_84000
    doc.lang = "bo"
    if fmt == "epub":
        text = "\n".join(_epub_files(doc).values())
    elif fmt == "docx":
        text = _docx_text(doc)
    else:
        text = render(doc, fmt)[0].decode("utf-8")
    assert "CBETA" not in text
    # 84000's terms: attribution must name 84000 itself, not just the translator.
    assert "84000: Translating the Words of the Buddha" in text
    assert "https://creativecommons.org/licenses/by-nc-nd/4.0/" in text


def test_non_cbeta_epub_identifier_and_language():
    doc = _doc(cbeta_id="84K-toh1")
    doc.source = _SRC_84000
    doc.lang = "bo"
    opf = _epub_files(doc)["OEBPS/content.opf"]
    assert "urn:fojin:84K-toh1" in opf
    assert "<dc:language>bo</dc:language>" in opf


def test_unknown_licence_is_stated_honestly():
    doc = _doc(cbeta_id="GRETIL-x")
    doc.source = _SRC_GRETIL
    text = render_txt(doc)
    assert "未查得該來源的許可聲明" in text
    assert "CBETA" not in text


async def test_build_export_doc_loads_source_licence():
    bt = _bt(id=7, cbeta_id="84K-toh1", lang="bo", source_id=3)
    ds = MagicMock()
    ds.code = "84000"
    ds.name_zh = "84000 藏传佛典翻译"
    ds.name_en = "84000: Translating the Words of the Buddha"
    ds.base_url = "https://read.84000.co"
    ds.license_spdx = "CC-BY-NC-ND-4.0"
    ds.license_url = "https://creativecommons.org/licenses/by-nc-nd/4.0/"
    text_result = MagicMock()
    text_result.scalar_one_or_none.return_value = bt
    content_result = MagicMock()
    content_result.scalars.return_value.all.return_value = [_content_row(1, "x")]
    src_result = MagicMock()
    src_result.scalar_one_or_none.return_value = ds
    session = AsyncMock()
    session.execute.side_effect = [text_result, content_result, src_result]
    doc = await build_export_doc(session, text_id=7, juan_num=None)
    assert doc.source.code == "84000"
    assert doc.source.license_spdx == "CC-BY-NC-ND-4.0"
    assert doc.text_id == 7 and doc.lang == "bo"
