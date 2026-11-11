"""OPDS 1.2 catalogue — lets e-book readers (Readest, KOReader, Moon+ Reader,
Thorium …) browse FoJin's canon and download whole texts as EPUB.

Only texts whose data source both appears in ``settings.opds_sources`` and has
``redistribution_allowed`` set are listed or downloadable: an OPDS feed is bulk
redistribution, so a source gets in only after its licence has been checked
(CBETA: CC BY-NC-SA 3.0 TW, verified 2026-11-11; its statement and version
information travel inside every EPUB on the closing 版權說明 page).

Feeds are plain Atom built with ElementTree. Every href is absolute and built
from ``settings.site_base_url`` — ``request.base_url`` is ``http://`` behind
nginx.
"""

import math
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from opencc import OpenCC
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.source import DataSource
from app.models.text import BuddhistText
from app.services.search_facets import SECTIONS
from app.services.text_export import build_export_doc, render

router = APIRouter(prefix="/opds", tags=["opds"])

ATOM = "http://www.w3.org/2005/Atom"
DC = "http://purl.org/dc/terms/"
OS = "http://a9.com/-/spec/opensearch/1.1/"
OPDS = "http://opds-spec.org/2010/catalog"
for _p, _ns in (("", ATOM), ("dc", DC), ("opensearch", OS), ("opds", OPDS)):
    ET.register_namespace(_p, _ns)

NAV_TYPE = "application/atom+xml;profile=opds-catalog;kind=navigation"
ACQ_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"
OPENSEARCH_TYPE = "application/opensearchdescription+xml"
EPUB_TYPE = "application/epub+zip"
ACQ_REL = "http://opds-spec.org/acquisition/open-access"

PAGE_SIZE = 50
_QUERY_MAX = 50

# Chinese labels for the Taishō sections in app.services.search_facets.SECTIONS.
SECTION_LABELS: dict[str, str] = {
    "agama": "阿含部",
    "jataka": "本緣部",
    "prajna": "般若部",
    "lotus": "法華部",
    "avatamsaka": "華嚴部",
    "ratnakuta": "寶積部",
    "nirvana": "涅槃部",
    "mahasamnipata": "大集部",
    "sutra_collection": "經集部",
    "esoteric": "密教部",
    "vinaya": "律部",
    "sutra_treatise": "釋經論部",
    "abhidharma": "毘曇部",
    "madhyamaka": "中觀部",
    "yogacara": "瑜伽部",
    "treatise_collection": "論集部",
    "sutra_commentary": "經疏部",
    "vinaya_commentary": "律疏部",
    "treatise_commentary": "論疏部",
    "schools": "諸宗部",
    "history": "史傳部",
    "encyclopedia": "事彙部",
    "non_buddhist": "外教部",
    "catalogue": "目錄部",
    "j_sutra_commentary": "續經疏部",
    "j_vinaya_commentary": "續律疏部",
    "j_treatise_commentary": "續論疏部",
    "j_schools": "續諸宗部",
    "siddham": "悉曇部",
    "dunhuang": "古逸部",
    "apocrypha": "疑似部",
}
_SECTION_RANGE = {code: (first, last) for code, first, last in SECTIONS}

_s2t = OpenCC("s2t")


# --- URLs --------------------------------------------------------------------

def _base() -> str:
    return settings.site_base_url.rstrip("/")


def _url(path: str) -> str:
    return f"{_base()}/api/opds{path}"


def download_url(text_id: int) -> str:
    return _url(f"/download/{text_id}.epub")


# --- query helpers -----------------------------------------------------------

def _listable() -> Select:
    """Texts that may appear in the catalogue: full text present, from a source
    on the OPDS allow-list whose licence permits redistribution."""
    return (
        select(BuddhistText)
        .join(DataSource, DataSource.id == BuddhistText.source_id)
        .where(
            BuddhistText.has_content.is_(True),
            DataSource.code.in_(settings.opds_sources),
            DataSource.redistribution_allowed.is_(True),
        )
    )


def _taisho_number(cbeta_id: str) -> int | None:
    if not cbeta_id.startswith("T"):
        return None
    digits = ""
    for ch in cbeta_id[1:]:
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else None


def _section_of(cbeta_id: str) -> str | None:
    n = _taisho_number(cbeta_id)
    if n is None:
        return None
    for code, first, last in SECTIONS:
        if first <= n <= last:
            return code
    return None


def _paginate(page: int, total: int) -> tuple[int, int]:
    pages = max(1, math.ceil(total / PAGE_SIZE))
    if page < 1 or page > pages:
        raise HTTPException(status_code=404, detail="page out of range")
    return pages, (page - 1) * PAGE_SIZE


# --- XML builders ------------------------------------------------------------

def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return _now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sub(parent: ET.Element, tag: str, text: str | None = None, ns: str = ATOM, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, _q(ns, tag), attrs)
    if text is not None:
        el.text = text
    return el


def _link(parent: ET.Element, rel: str, href: str, type_: str, title: str | None = None) -> None:
    attrs = {"rel": rel, "href": href, "type": type_}
    if title:
        attrs["title"] = title
    ET.SubElement(parent, _q(ATOM, "link"), attrs)


def _feed(feed_id: str, title: str, self_href: str, kind_type: str, up_href: str | None = None) -> ET.Element:
    feed = ET.Element(_q(ATOM, "feed"))
    _sub(feed, "id", feed_id)
    _sub(feed, "title", title)
    _sub(feed, "updated", _now())
    author = _sub(feed, "author")
    _sub(author, "name", "佛津 FoJin")
    _sub(author, "uri", _base())
    _sub(feed, "icon", f"{_base()}/favicon.ico")
    _link(feed, "self", self_href, kind_type)
    _link(feed, "start", _url(""), NAV_TYPE, "佛津書目")
    if up_href:
        _link(feed, "up", up_href, NAV_TYPE)
    _link(feed, "search", _url("/opensearch.xml"), OPENSEARCH_TYPE, "搜尋經名")
    return feed


def _nav_entry(feed: ET.Element, entry_id: str, title: str, href: str, summary: str, kind_type: str) -> None:
    entry = _sub(feed, "entry")
    _sub(entry, "title", title)
    _sub(entry, "id", entry_id)
    _sub(entry, "updated", _now())
    _sub(entry, "content", summary, type="text")
    _link(entry, "subsection", href, kind_type)


@dataclass
class _Book:
    id: int
    cbeta_id: str
    title: str
    translator: str | None
    dynasty: str | None
    fascicles: int | None
    lang: str
    created_at: datetime | None


def _book(bt: BuddhistText) -> _Book:
    return _Book(
        id=bt.id,
        cbeta_id=bt.cbeta_id,
        title=bt.title_zh,
        translator=bt.translator,
        dynasty=bt.dynasty,
        fascicles=bt.fascicle_count,
        lang=bt.lang or "lzh",
        created_at=bt.created_at,
    )


_LANG_TAGS = {"lzh": "zh-Hant", "pi": "pi", "sa": "sa", "bo": "bo", "en": "en"}


def _book_entry(feed: ET.Element, b: _Book) -> None:
    entry = _sub(feed, "entry")
    _sub(entry, "title", b.title)
    _sub(entry, "id", f"urn:cbeta:{b.cbeta_id}")
    _sub(entry, "updated", _iso(b.created_at))
    byline = " ".join(p for p in (b.dynasty, b.translator) if p)
    if byline:
        author = _sub(entry, "author")
        _sub(author, "name", byline)
    _sub(entry, "identifier", f"urn:cbeta:{b.cbeta_id}", ns=DC)
    _sub(entry, "language", _LANG_TAGS.get(b.lang, b.lang), ns=DC)
    _sub(entry, "publisher", "CBETA 電子佛典資料庫", ns=DC)
    parts = [f"CBETA {b.cbeta_id}"]
    if b.fascicles:
        parts.append(f"{b.fascicles} 卷")
    if byline:
        parts.append(byline)
    parts.append("CC BY-NC-SA 3.0 台灣，限非營利使用")
    _sub(entry, "summary", "；".join(parts), type="text")
    _link(entry, ACQ_REL, download_url(b.id), EPUB_TYPE, "下載 EPUB")
    _link(entry, "alternate", f"{_base()}/texts/{b.id}", "text/html", "在佛津閱讀")


def _pagination_links(feed: ET.Element, base_href: str, page: int, pages: int, total: int) -> None:
    sep = "&" if "?" in base_href else "?"

    def at(n: int) -> str:
        return f"{base_href}{sep}page={n}"

    _link(feed, "first", at(1), ACQ_TYPE)
    _link(feed, "last", at(pages), ACQ_TYPE)
    if page > 1:
        _link(feed, "previous", at(page - 1), ACQ_TYPE)
    if page < pages:
        _link(feed, "next", at(page + 1), ACQ_TYPE)
    _sub(feed, "totalResults", str(total), ns=OS)
    _sub(feed, "itemsPerPage", str(PAGE_SIZE), ns=OS)
    _sub(feed, "startIndex", str((page - 1) * PAGE_SIZE + 1), ns=OS)


def _xml(feed: ET.Element, media_type: str) -> Response:
    body = ET.tostring(feed, encoding="utf-8", xml_declaration=True)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


async def _books_page(db: AsyncSession, stmt: Select, page: int) -> tuple[list[_Book], int, int]:
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    if total == 0:
        return [], 0, 1
    pages, offset = _paginate(page, total)
    rows = (await db.execute(stmt.order_by(BuddhistText.cbeta_id).offset(offset).limit(PAGE_SIZE))).scalars().all()
    return [_book(r) for r in rows], total, pages


def _acq_feed(feed_id: str, title: str, href: str, up: str, books: Sequence[_Book], page: int, pages: int, total: int):
    sep = "&" if "?" in href else "?"
    feed = _feed(feed_id, title, f"{href}{sep}page={page}" if page > 1 else href, ACQ_TYPE, up)
    _pagination_links(feed, href, page, pages, total)
    for b in books:
        _book_entry(feed, b)
    return _xml(feed, ACQ_TYPE)


# --- routes ------------------------------------------------------------------

@router.get("")
async def root(db: AsyncSession = Depends(get_db)):
    """OPDS 根目錄（導航）：大正藏按部、卍續藏、搜尋。"""
    feed = _feed("urn:fojin:opds:root", "佛津 FoJin 漢文佛典書目", _url(""), NAV_TYPE)
    counts = await _prefix_counts(db)
    _nav_entry(
        feed,
        "urn:fojin:opds:taisho",
        "大正新脩大藏經",
        _url("/taisho"),
        f"按部瀏覽，共 {counts.get('T', 0)} 部（CBETA）",
        NAV_TYPE,
    )
    _nav_entry(
        feed,
        "urn:fojin:opds:xuzang",
        "卍新纂續藏經",
        _url("/xuzang"),
        f"按經號排列，共 {counts.get('X', 0)} 部（CBETA）",
        ACQ_TYPE,
    )
    return _xml(feed, NAV_TYPE)


async def _prefix_counts(db: AsyncSession) -> dict[str, int]:
    sub = _listable().with_only_columns(BuddhistText.cbeta_id).subquery()
    prefix = func.substr(sub.c.cbeta_id, 1, 1)
    rows = (await db.execute(select(prefix, func.count()).group_by(prefix))).all()
    return {p: n for p, n in rows}


@router.get("/taisho")
async def taisho_sections(db: AsyncSession = Depends(get_db)):
    """大正藏各部（導航）；空部不列。"""
    ids = (
        await db.execute(_listable().with_only_columns(BuddhistText.cbeta_id).where(BuddhistText.cbeta_id.like("T%")))
    ).scalars().all()
    counts: dict[str, int] = {}
    for cid in ids:
        code = _section_of(cid)
        if code:
            counts[code] = counts.get(code, 0) + 1
    feed = _feed("urn:fojin:opds:taisho", "大正新脩大藏經", _url("/taisho"), NAV_TYPE, _url(""))
    for code, first, last in SECTIONS:
        n = counts.get(code, 0)
        if not n:
            continue
        _nav_entry(
            feed,
            f"urn:fojin:opds:taisho:{code}",
            SECTION_LABELS.get(code, code),
            _url(f"/taisho/{code}"),
            f"T{first:04d}–T{last:04d}，{n} 部",
            ACQ_TYPE,
        )
    return _xml(feed, NAV_TYPE)


@router.get("/taisho/{section}")
async def taisho_section(section: str, page: int = Query(1, ge=1), db: AsyncSession = Depends(get_db)):
    """大正藏某一部的經目（可下載）。"""
    if section not in _SECTION_RANGE:
        raise HTTPException(status_code=404, detail="unknown section")
    first, last = _SECTION_RANGE[section]
    stmt = _listable().where(
        BuddhistText.cbeta_id.like("T%"),
        func.substring(BuddhistText.cbeta_id, 2, 4).between(f"{first:04d}", f"{last:04d}"),
    )
    books, total, pages = await _books_page(db, stmt, page)
    label = SECTION_LABELS.get(section, section)
    return _acq_feed(
        f"urn:fojin:opds:taisho:{section}",
        f"大正藏・{label}",
        _url(f"/taisho/{section}"),
        _url("/taisho"),
        books,
        page,
        pages,
        total,
    )


@router.get("/xuzang")
async def xuzang(page: int = Query(1, ge=1), db: AsyncSession = Depends(get_db)):
    """卍續藏經目（按經號，可下載）。"""
    stmt = _listable().where(BuddhistText.cbeta_id.like("X%"))
    books, total, pages = await _books_page(db, stmt, page)
    return _acq_feed("urn:fojin:opds:xuzang", "卍新纂續藏經", _url("/xuzang"), _url(""), books, page, pages, total)


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=_QUERY_MAX),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """按經名或經號搜尋；簡體輸入會轉成繁體一併比對。"""
    term = q.strip()
    if not term:
        raise HTTPException(status_code=422, detail="empty query")
    variants = {term, _s2t.convert(term)}
    clauses = [BuddhistText.title_zh.contains(v, autoescape=True) for v in variants]
    clauses.append(func.upper(BuddhistText.cbeta_id) == term.upper())
    stmt = _listable().where(or_(*clauses))
    books, total, pages = await _books_page(db, stmt, page)
    href = _url(f"/search?q={quote(term)}")
    return _acq_feed(f"urn:fojin:opds:search:{term}", f"搜尋：{term}", href, _url(""), books, page, pages, total)


@router.get("/opensearch.xml")
async def opensearch():
    """OpenSearch 描述檔，閱讀器據此顯示搜尋框。"""
    root = ET.Element(_q(OS, "OpenSearchDescription"))
    ET.SubElement(root, _q(OS, "ShortName")).text = "佛津"
    ET.SubElement(root, _q(OS, "Description")).text = "搜尋佛津書目中的經名或經號"
    ET.SubElement(root, _q(OS, "InputEncoding")).text = "UTF-8"
    ET.SubElement(root, _q(OS, "OutputEncoding")).text = "UTF-8"
    ET.SubElement(
        root,
        _q(OS, "Url"),
        {"type": ACQ_TYPE, "template": _url("/search?q={searchTerms}")},
    )
    body = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(content=body, media_type=OPENSEARCH_TYPE, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/download/{text_id}.epub")
async def download(text_id: int, db: AsyncSession = Depends(get_db)):
    """下載整部經的 EPUB（只限書目內的經）。"""
    allowed = (await db.execute(_listable().with_only_columns(BuddhistText.id).where(BuddhistText.id == text_id))).first()
    if allowed is None:
        raise HTTPException(status_code=404, detail="not in catalogue")
    doc = await build_export_doc(db, text_id, None)
    if doc is None:
        raise HTTPException(status_code=404, detail="no content")
    payload, media_type = render(doc, "epub")
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.cbeta_id}.epub"',
            "Cache-Control": "public, max-age=86400",
        },
    )
