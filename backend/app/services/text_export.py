"""Single-text document export — render one sutra (whole or one juan) as a
downloadable TXT / HTML / DOCX / EPUB document.

Design notes:
- The export is assembled from the stored per-juan plain content (already
  CBETA-cleaned, one source line per physical line). We split on newlines and
  drop blank lines; no reflow — a document export favours fidelity to the
  source lines over the reader's prose/verse heuristics.
- EPUB is built by hand with the stdlib ``zipfile`` (an EPUB is just a ZIP of
  XHTML + OPF + NCX). This keeps the dependency surface flat — no ebooklib.
- DOCX uses ``python-docx`` which is already a dependency.
- The pure ``render_*`` functions take an in-memory ``ExportDoc`` and return
  bytes, so they are unit-testable without a database.
"""

import re
from dataclasses import dataclass, field
from html import escape
from io import BytesIO
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.source import DataSource
from app.models.text import BuddhistText, TextContent
from app.services.text_reflow import Segment, reflow

# format → (file extension, media type)
FORMATS: dict[str, tuple[str, str]] = {
    "txt": (".txt", "text/plain; charset=utf-8"),
    "html": (".html", "text/html; charset=utf-8"),
    "docx": (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "epub": (".epub", "application/epub+zip"),
}

# EPUB 3 requires exactly one dcterms:modified. A fixed constant keeps re-exports
# byte-stable (the content itself, not the export time, is what identifies an
# edition) while satisfying epubcheck RSC-005.
_EPUB_MODIFIED = "2026-01-01T00:00:00Z"


@dataclass
class ExportJuan:
    juan_num: int
    # Raw stripped source lines — used by TXT (no layout) and as the reflow input.
    lines: list[str] = field(default_factory=list)
    # Reflowed layout segments — used by HTML/EPUB/DOCX to match the web reader.
    segments: list[Segment] = field(default_factory=list)


@dataclass
class ExportSource:
    """Where the text came from and under what terms — drives the source line,
    the EPUB rights metadata and the closing 版權說明 page of every export."""

    code: str | None = None
    name_zh: str | None = None
    name_en: str | None = None
    base_url: str | None = None
    license_spdx: str | None = None
    license_url: str | None = None


# CBETA's own statement (https://www.cbeta.org/copyright.php, read 2026-11-11).
# Its 使用說明 makes this a condition of redistribution: "將本資料庫以網路、光碟或
# 其它媒體再傳播……需於成品附上本說明及版本資訊". Keep the wording verbatim.
CBETA_STATEMENT: tuple[str, ...] = (
    "CBETA 電子佛典資料庫使用說明：",
    "本資料庫之使用限定於個人或團體非營利性用途。若運用於營利性目的時，"
    "必須事先取得本會與該底本版權者之同意。",
    "將本資料庫以網路、光碟或其它媒體再傳播、節錄引用及再加工發行時，"
    "以不改變實質內容為原則，並需於成品附上本說明及版本資訊，以利使用者查詢相關修訂資訊。",
    "若發現本資料庫中任何錯誤之處，請與本會聯絡。",
    "若因使用本資料庫所產生之任何損害，本會一概不負任何責任。",
)
CBETA_LICENSE_NAME = "Creative Commons 姓名標示-非商業性-相同方式分享 3.0 台灣 (中華民國) 授權條款"
CBETA_LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/3.0/tw/"
CBETA_COPYRIGHT_URL = "https://www.cbeta.org/copyright.php"
# 版本資訊: which CBETA release the text was taken from. FoJin imported the
# cbeta-org/xml-p5 repository in 2026-03/04 (text_contents.created_at on prod).
CBETA_VERSION = "CBETA XML P5（https://github.com/cbeta-org/xml-p5），佛津於 2026 年 3–4 月匯入"

# FoJin's own processing, stated so readers can tell it apart from the source.
# Deliberately not "未改動經文文字": import normalises gaiji and joins hard-wrapped
# lines, and nobody has diffed the result against CBETA character by character.
FOJIN_PROCESSING = "佛津（FoJin）依原文重新排版（分段、偈頌縮排）；如與原始來源有出入，以原始來源為準。"

_LANG_TAGS = {"lzh": "zh-Hant", "pi": "pi", "sa": "sa", "bo": "bo", "en": "en"}


@dataclass
class ExportDoc:
    title: str
    cbeta_id: str
    translator: str | None = None
    dynasty: str | None = None
    juans: list[ExportJuan] = field(default_factory=list)
    text_id: int | None = None
    lang: str = "lzh"
    source: ExportSource = field(default_factory=lambda: ExportSource(code="cbeta"))


def _byline(doc: ExportDoc) -> str:
    """'後秦 佛陀耶舍譯'-style attribution line, omitting missing parts."""
    return " ".join(p for p in (doc.dynasty, doc.translator) if p)


_CN_DIGITS = "〇一二三四五六七八九"


def cn_number(n: int) -> str:
    """1..9999 in the canon's own style: 十, 十一, 二十一, 一百, 一百五, 一百一十, 六百."""
    if n <= 0 or n >= 10000:
        return str(n)
    parts = []
    for value, unit in ((1000, "千"), (100, "百"), (10, "十")):
        d, n = divmod(n, value)
        if d:
            parts.append(("" if (unit == "十" and not parts and d == 1) else _CN_DIGITS[d]) + unit)
        # A skipped place gets no 零: CBETA writes 一百五, not 一百零五.
    if n:
        parts.append(_CN_DIGITS[n])
    return "".join(parts)


def _juan_label(juan_num: int) -> str:
    return f"卷第{cn_number(juan_num)}"


_URL_RE = re.compile(r"https?://[^\s，。；（）()<>\"]+")


def _linkify(escaped: str) -> str:
    """Make bare URLs in already-escaped (X)HTML text clickable."""
    return _URL_RE.sub(lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>', escaped)


def _is_cbeta(doc: ExportDoc) -> bool:
    return doc.source.code == "cbeta"


def _lang_tag(doc: ExportDoc) -> str:
    return _LANG_TAGS.get(doc.lang, doc.lang or "und")


def source_line(doc: ExportDoc) -> str:
    """Short source label under the title: 'CBETA T0001', or the real source's
    name for non-CBETA texts (they used to be mislabelled 'CBETA …')."""
    if _is_cbeta(doc):
        return f"CBETA {doc.cbeta_id}"
    name = doc.source.name_en or doc.source.name_zh
    return f"{name} {doc.cbeta_id}" if name else doc.cbeta_id


def reader_url(doc: ExportDoc) -> str | None:
    if doc.text_id is None:
        return None
    return f"{settings.site_base_url.rstrip('/')}/texts/{doc.text_id}"


def rights_summary(doc: ExportDoc) -> str:
    """One-line rights statement for EPUB dc:rights."""
    if _is_cbeta(doc):
        return f"CBETA 電子佛典資料庫，{CBETA_LICENSE_NAME}（{CBETA_LICENSE_URL}）；限非營利使用。"
    src = doc.source
    name = src.name_en or src.name_zh or "原始來源"
    if src.license_spdx:
        tail = f"（{src.license_url}）" if src.license_url else ""
        return f"{name}，{src.license_spdx}{tail}"
    return f"{name}，許可條款未標明"


def colophon_lines(doc: ExportDoc) -> list[str]:
    """The closing 版權說明 page, as plain lines (each format renders them)."""
    out: list[str] = []
    if _is_cbeta(doc):
        out.append("經文出處：CBETA 電子佛典資料庫，財團法人佛教電子佛典基金會（原中華電子佛典協會）")
        out.append(f"經號：{doc.cbeta_id}")
        out.append(f"版本資訊：{CBETA_VERSION}")
        out.append(f"授權條款：{CBETA_LICENSE_NAME}，{CBETA_LICENSE_URL}")
        out.extend(CBETA_STATEMENT)
        out.append(f"完整版權宣告：{CBETA_COPYRIGHT_URL}")
    else:
        src = doc.source
        names = " / ".join(n for n in (src.name_zh, src.name_en) if n)
        out.append(f"經文出處：{names or '原始來源'}" + (f"，{src.base_url}" if src.base_url else ""))
        out.append(f"編號：{doc.cbeta_id}")
        if src.license_spdx:
            out.append(f"授權條款：{src.license_spdx}" + (f"，{src.license_url}" if src.license_url else ""))
        else:
            out.append("授權條款：佛津未查得該來源的許可聲明，再利用前請向原始來源確認。")
    out.append(FOJIN_PROCESSING)
    url = reader_url(doc)
    if url:
        out.append(f"佛津線上閱讀（校勘、注疏、引文核對）：{url}")
    return out


COLOPHON_TITLE = "版權說明"


# --- TXT ---------------------------------------------------------------------

def render_txt(doc: ExportDoc) -> str:
    out: list[str] = [doc.title]
    byline = _byline(doc)
    if byline:
        out.append(byline)
    out.append(source_line(doc))
    for j in doc.juans:
        out.append("")
        out.append(_juan_label(j.juan_num))
        out.append("")
        out.extend(j.lines)
    out.append("")
    out.append(f"—— {COLOPHON_TITLE} ——")
    out.extend(colophon_lines(doc))
    return "\n".join(out) + "\n"


# --- HTML --------------------------------------------------------------------

# Mirrors the web reader's reader.css typography (.text-prose/.text-verse/…) so
# the exported page reads like fojin.app: flowing prose paragraphs (2em indent),
# indented verse, centred juan/section headings, right-aligned byline.
_HTML_STYLE = (
    "body{font-family:'Noto Serif SC','Source Han Serif SC',serif;max-width:42em;"
    "margin:2em auto;padding:0 1.2em;line-height:1.8;color:#1a1a1a;"
    "line-break:strict}"
    "h1{font-size:1.5em;margin:0 0 .2em}"
    ".byline-doc{color:#666;margin:0 0 .1em}.src{color:#999;font-size:.85em;margin:0 0 1.5em}"
    ".juan{font-size:1.1em;color:#8b6914;text-align:center;margin:1.5em 0 1em}"
    ".head{font-size:1.2em;color:#8b6914;text-align:center;margin:.5em 0 1em}"
    ".byline{color:#408080;text-align:right;margin:0 0 1.2em;font-size:.95em}"
    ".section{text-align:center;margin:1.5em 0 1em;font-size:1.05em}"
    ".prose{text-indent:2em;margin:0 0 1em}"
    ".verse{margin:0;padding-left:4em;text-indent:0}"
    ".colophon{margin-top:3em;padding-top:1em;border-top:1px solid #ddd;color:#666;font-size:.85em}"
    ".colophon h2{font-size:1em;color:#666}"
)


def _seg_html(seg: Segment) -> str:
    if seg.type == "break":
        return ""
    return f'<p class="{seg.type}">{escape(seg.text)}</p>'


def render_html(doc: ExportDoc) -> str:
    parts: list[str] = [
        "<!DOCTYPE html>",
        f'<html lang="{_lang_tag(doc)}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(doc.title)}</title>",
        f"<style>{_HTML_STYLE}</style>",
        "</head>",
        "<body>",
        f"<h1>{escape(doc.title)}</h1>",
    ]
    byline = _byline(doc)
    if byline:
        parts.append(f'<p class="byline-doc">{escape(byline)}</p>')
    parts.append(f'<p class="src">{escape(source_line(doc))}</p>')
    for j in doc.juans:
        parts.append(f'<h2 class="juan">{escape(_juan_label(j.juan_num))}</h2>')
        parts.extend(html for html in (_seg_html(s) for s in j.segments) if html)
    parts.append(f'<section class="colophon"><h2>{COLOPHON_TITLE}</h2>')
    parts.extend(f"<p>{_linkify(escape(line))}</p>" for line in colophon_lines(doc))
    parts.append("</section>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


# --- DOCX --------------------------------------------------------------------

def render_docx(doc: ExportDoc) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    d = Document()
    d.add_heading(doc.title, level=0)
    byline = _byline(doc)
    if byline:
        d.add_paragraph(byline)
    d.add_paragraph(source_line(doc))
    for j in doc.juans:
        d.add_heading(_juan_label(j.juan_num), level=1)
        for seg in j.segments:
            if seg.type == "break":
                continue
            if seg.type in ("head", "juan"):
                h = d.add_heading(seg.text, level=2)
                h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                continue
            p = d.add_paragraph(seg.text)
            if seg.type == "section":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif seg.type == "byline":
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            elif seg.type == "prose":
                p.paragraph_format.first_line_indent = Pt(24)
            elif seg.type == "verse":
                p.paragraph_format.left_indent = Pt(48)
    d.add_heading(COLOPHON_TITLE, level=1)
    for line in colophon_lines(doc):
        d.add_paragraph(line)
    buf = BytesIO()
    d.save(buf)
    return buf.getvalue()


# --- EPUB --------------------------------------------------------------------

# Inline CSS shared by every juan document — same typography as the HTML export.
_EPUB_CSS = (
    "body{font-family:'Noto Serif SC',serif;line-height:1.8}"
    ".juan{font-size:1.1em;text-align:center;margin:1.5em 0 1em}"
    ".head{font-size:1.2em;text-align:center;margin:.5em 0 1em}"
    ".byline{text-align:right;margin:0 0 1.2em;font-size:.95em}"
    ".section{text-align:center;margin:1.5em 0 1em}"
    ".prose{text-indent:2em;margin:0 0 1em}"
    ".verse{margin:0;padding-left:4em}"
)


def _seg_xhtml(seg: Segment) -> str:
    if seg.type == "break":
        return ""
    return f'    <p class="{seg.type}">{xml_escape(seg.text)}</p>'


def _epub_juan_xhtml(title: str, j: ExportJuan, lang: str = "zh-Hant") -> str:
    body = "\n".join(x for x in (_seg_xhtml(s) for s in j.segments) if x)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}">\n'
        f"  <head><title>{xml_escape(title)} {_juan_label(j.juan_num)}</title>\n"
        '  <meta charset="utf-8"/>\n'
        f"  <style>{_EPUB_CSS}</style></head>\n"
        "  <body>\n"
        f'    <h2 class="juan">{xml_escape(_juan_label(j.juan_num))}</h2>\n'
        f"{body}\n"
        "  </body>\n"
        "</html>\n"
    )


_COLOPHON_FILE = "colophon.xhtml"


def _epub_colophon_xhtml(doc: ExportDoc) -> str:
    body = "\n".join(f"    <p>{_linkify(xml_escape(line))}</p>" for line in colophon_lines(doc))
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-Hant">\n'
        f"  <head><title>{COLOPHON_TITLE}</title>\n"
        '  <meta charset="utf-8"/>\n'
        "  <style>body{font-family:'Noto Serif SC',serif;line-height:1.7;font-size:.9em}"
        "h2{font-size:1.1em;text-align:center;margin:1em 0}p{margin:0 0 .8em}</style></head>\n"
        '  <body epub:type="colophon">\n'
        f"    <h2>{COLOPHON_TITLE}</h2>\n"
        f"{body}\n"
        "  </body>\n"
        "</html>\n"
    )


def render_epub(doc: ExportDoc) -> bytes:
    # Deterministic id so re-exports are byte-stable and the OPF is verifiable.
    # Only CBETA texts carry a CBETA number; others get a FoJin URN.
    book_id = f"urn:cbeta:{doc.cbeta_id}" if _is_cbeta(doc) else f"urn:fojin:{doc.cbeta_id}"
    lang = _lang_tag(doc)
    juan_files = [(f"juan{j.juan_num}.xhtml", j) for j in doc.juans]

    manifest_items = "\n".join(
        f'    <item id="j{j.juan_num}" href="{fn}" media-type="application/xhtml+xml"/>'
        for fn, j in juan_files
    )
    manifest_items += f'\n    <item id="colophon" href="{_COLOPHON_FILE}" media-type="application/xhtml+xml"/>'
    spine_items = "\n".join(f'    <itemref idref="j{j.juan_num}"/>' for _, j in juan_files)
    spine_items += '\n    <itemref idref="colophon"/>'
    byline = _byline(doc)
    creator = f"<dc:creator>{xml_escape(byline)}</dc:creator>" if byline else ""
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f'    <dc:identifier id="bookid">{xml_escape(book_id)}</dc:identifier>\n'
        f"    <dc:title>{xml_escape(doc.title)}</dc:title>\n"
        f"    <dc:language>{xml_escape(lang)}</dc:language>\n"
        f"    {creator}\n"
        f"    <dc:source>{xml_escape(source_line(doc))}</dc:source>\n"
        f"    <dc:rights>{xml_escape(rights_summary(doc))}</dc:rights>\n"
        "    <dc:publisher>佛津 FoJin（fojin.app）</dc:publisher>\n"
        f'    <meta property="dcterms:modified">{_EPUB_MODIFIED}</meta>\n'
        "  </metadata>\n"
        "  <manifest>\n"
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
        f"{manifest_items}\n"
        "  </manifest>\n"
        "  <spine>\n"
        f"{spine_items}\n"
        "  </spine>\n"
        "</package>\n"
    )

    nav_links = "\n".join(
        f'      <li><a href="{fn}">{xml_escape(_juan_label(j.juan_num))}</a></li>'
        for fn, j in juan_files
    )
    nav_links += f'\n      <li><a href="{_COLOPHON_FILE}">{COLOPHON_TITLE}</a></li>'
    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-Hant">\n'
        f"  <head><title>{xml_escape(doc.title)}</title></head>\n"
        "  <body>\n"
        '    <nav epub:type="toc">\n'
        f"      <h1>{xml_escape(doc.title)}</h1>\n"
        "      <ol>\n"
        f"{nav_links}\n"
        "      </ol>\n"
        "    </nav>\n"
        "  </body>\n"
        "</html>\n"
    )

    container = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>\n"
    )

    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
        # OCF rule: 'mimetype' first, stored uncompressed.
        zf.writestr(ZipInfo("mimetype"), "application/epub+zip", compress_type=ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/nav.xhtml", nav)
        for fn, j in juan_files:
            zf.writestr(f"OEBPS/{fn}", _epub_juan_xhtml(doc.title, j, lang))
        zf.writestr(f"OEBPS/{_COLOPHON_FILE}", _epub_colophon_xhtml(doc))
    return buf.getvalue()


# --- dispatch ----------------------------------------------------------------

def render(doc: ExportDoc, fmt: str) -> tuple[bytes, str]:
    """Render ``doc`` to ``fmt``; returns (payload_bytes, media_type)."""
    if fmt not in FORMATS:
        raise ValueError(f"unsupported export format: {fmt!r}")
    _, media_type = FORMATS[fmt]
    if fmt == "txt":
        return render_txt(doc).encode("utf-8"), media_type
    if fmt == "html":
        return render_html(doc).encode("utf-8"), media_type
    if fmt == "docx":
        return render_docx(doc), media_type
    return render_epub(doc), media_type


# --- DB assembly -------------------------------------------------------------

def _split_lines(content: str) -> list[str]:
    return [ln.strip() for ln in content.split("\n") if ln.strip()]


async def build_export_doc(
    session: AsyncSession, text_id: int, juan_num: int | None
) -> ExportDoc | None:
    """Assemble an ExportDoc from stored content. ``juan_num=None`` exports the
    whole text; otherwise just that one juan. Returns None if the text is
    unknown or has no content."""
    result = await session.execute(select(BuddhistText).where(BuddhistText.id == text_id))
    bt = result.scalar_one_or_none()
    if bt is None:
        return None

    query = (
        select(TextContent)
        .where(TextContent.text_id == text_id, TextContent.lang == bt.lang)
        .order_by(TextContent.juan_num)
    )
    if juan_num is not None:
        query = query.where(TextContent.juan_num == juan_num)
    result = await session.execute(query)
    rows = result.scalars().all()
    if not rows:
        return None

    juans = [
        ExportJuan(
            juan_num=r.juan_num,
            lines=_split_lines(r.content or ""),
            segments=reflow(r.content or ""),
        )
        for r in rows
    ]
    source = ExportSource()
    if bt.source_id is not None:
        result = await session.execute(select(DataSource).where(DataSource.id == bt.source_id))
        ds = result.scalar_one_or_none()
        if ds is not None:
            source = ExportSource(
                code=ds.code,
                name_zh=ds.name_zh,
                name_en=ds.name_en,
                base_url=ds.base_url,
                license_spdx=ds.license_spdx,
                license_url=ds.license_url,
            )
    return ExportDoc(
        title=bt.title_zh,
        cbeta_id=bt.cbeta_id,
        translator=bt.translator,
        dynasty=bt.dynasty,
        juans=juans,
        text_id=bt.id,
        lang=bt.lang or "lzh",
        source=source,
    )
