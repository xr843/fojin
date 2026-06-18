"""
CBETA TEI P5 XML parser.

Parses CBETA XML files and extracts plain text content split by juan (fascicle).
Handles <milestone unit="juan">, <cb:juan>, <p>, <lg>/<l>, <head> elements.
Skips <note>, <app> (critical apparatus) elements.
Resolves gaiji (缺字) via cbeta_gaiji.json for PUA characters.
"""

import json
import logging
import re
from pathlib import Path

import httpx
from lxml import etree

logger = logging.getLogger(__name__)

# CBETA TEI namespace
TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"
NSMAP = {"tei": TEI_NS, "cb": CB_NS}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

# <anchor> and <lb> markers are emitted into the extracted text as control-char
# sentinels (\x00 never appears in CBETA text) so their position within the
# FINAL cleaned juan content can be recovered. They are stripped out before the
# content is stored; the recovered offsets drive the standoff critical apparatus
# (校勘异文) and <lb> page-col-line anchors.
#   anchor:  \x00A:<xml:id>\x00      line:  \x00L:<n>\x00
_SENTINEL_RE = re.compile("\x00([AL]):([^\x00]*)\x00")

# Elements whose text content we want to extract (leaf content elements)
CONTENT_TAGS = {
    f"{{{TEI_NS}}}p",
    f"{{{TEI_NS}}}l",       # verse line
    f"{{{TEI_NS}}}head",
    f"{{{TEI_NS}}}item",    # list entries — catalog/科文 texts (T2178-2182, X "科" series) are entirely <list><item>
}

# Elements to skip entirely (including their children)
SKIP_TAGS = {
    f"{{{TEI_NS}}}note",
    f"{{{TEI_NS}}}app",
    f"{{{TEI_NS}}}rdg",
    f"{{{TEI_NS}}}ref",
    f"{{{CB_NS}}}tt",       # translation table
    f"{{{CB_NS}}}mulu",     # table of contents entry (e.g. "2" in juan heading)
}

# CBETA gaiji (缺字) mapping: CB ID → best available character
_GAIJI_MAP: dict[str, str] = {}
_GAIJI_LOADED = False

GAIJI_JSON_URL = "https://raw.githubusercontent.com/cbeta-org/cbeta_gaiji/master/cbeta_gaiji.json"
GAIJI_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "cbeta_gaiji.json"


def _is_pua(c: str) -> bool:
    """Check if a character is in a Private Use Area (displays as □)."""
    cp = ord(c)
    return (0xE000 <= cp <= 0xF8FF) or (0xF0000 <= cp <= 0xFFFFD) or (0x100000 <= cp <= 0x10FFFD)


def _load_gaiji():
    """Load CBETA gaiji mapping from local cache or remote."""
    global _GAIJI_MAP, _GAIJI_LOADED
    if _GAIJI_LOADED:
        return

    # Try local cache first
    if GAIJI_CACHE_PATH.exists():
        try:
            raw = json.loads(GAIJI_CACHE_PATH.read_text(encoding="utf-8"))
            _build_gaiji_map(raw)
            _GAIJI_LOADED = True
            logger.info("Loaded %d gaiji entries from cache", len(_GAIJI_MAP))
            return
        except Exception:
            logger.warning("Failed to load gaiji cache, will download", exc_info=True)

    # Download from GitHub
    try:
        resp = httpx.get(GAIJI_JSON_URL, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        raw = resp.json()
        # Save cache
        GAIJI_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        GAIJI_CACHE_PATH.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        _build_gaiji_map(raw)
        _GAIJI_LOADED = True
        logger.info("Downloaded and cached %d gaiji entries", len(_GAIJI_MAP))
    except Exception:
        logger.warning("Failed to download gaiji mapping", exc_info=True)
        _GAIJI_LOADED = True  # Don't retry on every call


def _build_gaiji_map(raw: dict):
    """Build CB ID → best character mapping from cbeta_gaiji.json."""
    for cb_id, info in raw.items():
        # Priority: uni_char > norm_uni_char > norm_big5_char > composition
        char = info.get("uni_char") or ""
        if char and not any(_is_pua(c) for c in char):
            _GAIJI_MAP[cb_id] = char
            continue
        norm = info.get("norm_uni_char") or info.get("norm_big5_char") or ""
        if norm:
            _GAIJI_MAP[cb_id] = norm
            continue
        comp = info.get("composition") or ""
        if comp:
            _GAIJI_MAP[cb_id] = comp


def _resolve_gaiji(elem) -> str:
    """Resolve a <g ref="#CBxxxxx"> element to its best Unicode character."""
    _load_gaiji()
    ref = elem.get("ref", "")
    cb_id = ref.lstrip("#") if ref.startswith("#") else ref

    # Try gaiji map
    if cb_id and cb_id in _GAIJI_MAP:
        return _GAIJI_MAP[cb_id]

    # Fallback: use the element's text content if it's not PUA
    text = elem.text or ""
    if text and not any(_is_pua(c) for c in text):
        return text

    # Last resort: try to extract from the charDecl in the same document
    return "□"


def _extract_text(elem) -> str:
    """Recursively extract text from an element, skipping note/app elements."""
    parts = []

    if elem.tag in SKIP_TAGS:
        return ""

    if elem.text:
        parts.append(elem.text)

    for child in elem:
        if child.tag in SKIP_TAGS:
            # Skip this child but get its tail
            if child.tail:
                parts.append(child.tail)
        elif child.tag == f"{{{TEI_NS}}}g":
            # Resolve gaiji (缺字) to best available character
            parts.append(_resolve_gaiji(child))
            if child.tail:
                parts.append(child.tail)
        elif child.tag == f"{{{TEI_NS}}}anchor":
            # Standoff apparatus anchor — emit a sentinel so its offset in the
            # cleaned content can be recovered (see _clean_anchors).
            aid = child.get(XML_ID)
            if aid:
                parts.append(f"\x00A:{aid}\x00")
            if child.tail:
                parts.append(child.tail)
        elif child.tag == f"{{{TEI_NS}}}lb":
            # Page-column-line marker (e.g. n="0001a09").
            n = child.get("n")
            if n:
                parts.append(f"\x00L:{n}\x00")
            if child.tail:
                parts.append(child.tail)
        else:
            parts.append(_extract_text(child))
            if child.tail:
                parts.append(child.tail)

    return "".join(parts)


def _extract_reading_text(elem) -> str:
    """Extract the textual reading of an apparatus <lem>/<rdg>.

    Unlike _extract_text this does NOT bail on SKIP_TAGS — <rdg> is itself a
    skip tag in the body, but here we want its content. Resolves gaiji, drops
    nested editorial <note>, and treats <space> (omission) as empty.
    """
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        ctag = child.tag
        if ctag == f"{{{TEI_NS}}}g":
            parts.append(_resolve_gaiji(child))
        elif ctag in (f"{{{TEI_NS}}}note", f"{{{TEI_NS}}}space"):
            pass
        else:
            parts.append(_extract_reading_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _clean_anchors(text: str) -> tuple[str, dict[str, int], list[dict]]:
    """Strip anchor/line sentinels from text, recovering their char offsets.

    Returns (clean_text, {anchor_id: offset}, [{"offset": o, "line": ref}]).
    Offsets are indices into clean_text. Walking sentinels left-to-right and
    tracking only the cleaned length keeps every offset exact.
    """
    anchors: dict[str, int] = {}
    line_anchors: list[dict] = []
    out: list[str] = []
    clean_len = 0
    i = 0
    for m in _SENTINEL_RE.finditer(text):
        chunk = text[i:m.start()]
        out.append(chunk)
        clean_len += len(chunk)
        kind, payload = m.group(1), m.group(2)
        if kind == "A":
            anchors[payload] = clean_len
        else:
            line_anchors.append({"offset": clean_len, "line": payload})
        i = m.end()
    out.append(text[i:])
    return "".join(out), anchors, line_anchors


def parse_tei_xml(xml_path: str | Path) -> list[dict]:
    """
    Parse a CBETA TEI XML file and return a list of juan dicts.

    Returns:
        [{"juan_num": 1, "content": "...", "char_count": N}, ...]
    """
    xml_path = Path(xml_path)
    if not xml_path.exists():
        return []

    try:
        tree = etree.parse(str(xml_path))
    except etree.XMLSyntaxError:
        return []
    root = tree.getroot()

    # Find <body> element
    body = root.find(f".//{{{TEI_NS}}}body")
    if body is None:
        return []

    juans: list[dict] = []
    current_juan = 1
    current_lines: list[str] = []
    preface_lines: list[str] = []  # sidelined <cb:div type="xu"> paratext

    def flush_juan():
        nonlocal current_lines
        # Keep blank lines (paragraph boundaries) but strip leading/trailing empties
        text = "\n".join(current_lines)
        text = text.strip()
        clean, anchors, line_anchors = _clean_anchors(text)
        if clean:
            juans.append({
                "juan_num": current_juan,
                "content": clean,
                "char_count": len(clean.replace("\n", "").replace(" ", "")),
                "anchors": anchors,
                "line_anchors": line_anchors,
            })
        current_lines = []

    def process_element(elem):
        nonlocal current_juan, current_lines, preface_lines

        tag = elem.tag

        # Check for juan boundaries
        if tag == f"{{{TEI_NS}}}milestone":
            unit = elem.get("unit", "")
            if unit == "juan":
                # New juan starts
                flush_juan()
                n = elem.get("n", "")
                try:
                    current_juan = int(n)
                except ValueError:
                    current_juan += 1
                return

        if tag == f"{{{CB_NS}}}juan":
            fun = elem.get("fun", "")
            if fun == "open":
                # Only use cb:juan to set juan_num if no milestone preceded it.
                # When milestone already set current_juan, cb:juan just provides title text.
                n = elem.get("n", "")
                n_clean = re.sub(r"[^0-9]", "", n)  # "001a" → "1"
                if n_clean:
                    juan_int = int(n_clean)
                    if juan_int != current_juan:
                        # Different juan — flush and update
                        flush_juan()
                        current_juan = juan_int
                # Extract juan title text (e.g. "阿毘達磨俱舍論卷第一")
                juan_text = _extract_text(elem).strip()
                if juan_text:
                    current_lines.append(juan_text)
            return

        # Extract byline (author/translator info)
        if tag == f"{{{TEI_NS}}}byline":
            text = _extract_text(elem).strip()
            if text:
                current_lines.append(text)
            return

        # Skip certain elements
        if tag in SKIP_TAGS:
            return

        # Extract text from content elements
        if tag in CONTENT_TAGS:
            text = _extract_text(elem).strip()
            if text:
                # Insert blank line between <p> elements to preserve paragraph
                # boundaries. The frontend reflowText handles mid-word splits
                # by only breaking when the previous line ends with punctuation.
                if tag == f"{{{TEI_NS}}}p" and current_lines:
                    current_lines.append("")
                current_lines.append(text)
            return

        # For <lg> (verse group), process children
        if tag == f"{{{TEI_NS}}}lg":
            for child in elem:
                process_element(child)
            return

        # Sideline front-matter preface divs (序 / type="xu"). These are paratext
        # — e.g. the imperial 御製序 prepended to short sutras like 心經 (T0251) —
        # which would otherwise fold into juan 1, bury the scripture body, and
        # cripple RAG recall of the root text. Captured separately (not into
        # current_lines) so it is excluded from the scripture body, yet still
        # available as a fallback below if a work has NO other content (some
        # CBETA fragments are preface-only) — never silently emptied.
        # Deliberately narrow: only type="xu", not a general front-matter filter.
        if tag == f"{{{CB_NS}}}div" and elem.get("type") == "xu":
            preface_text = _extract_text(elem).strip()
            if preface_text:
                preface_lines.append(preface_text)
            return

        # For div/cb:div and other container elements, recurse
        if tag in (f"{{{TEI_NS}}}div", f"{{{CB_NS}}}div",
                   f"{{{TEI_NS}}}body", f"{{{TEI_NS}}}text",
                   f"{{{TEI_NS}}}front", f"{{{TEI_NS}}}back"):
            for child in elem:
                process_element(child)
            return

        # For other elements that might contain text
        for child in elem:
            process_element(child)

    process_element(body)
    flush_juan()

    # If no juans were found but there is content, treat everything as juan 1
    if not juans and current_lines:
        text = "\n".join(line for line in current_lines if line.strip()).strip()
        clean, anchors, line_anchors = _clean_anchors(text)
        if clean:
            juans.append({
                "juan_num": 1,
                "content": clean,
                "char_count": len(clean.replace("\n", "").replace(" ", "")),
                "anchors": anchors,
                "line_anchors": line_anchors,
            })

    # Last resort: a preface-only work (no scripture body at all). Emit the
    # sidelined paratext rather than returning [] — which import_work would
    # silently skip, leaving the work with has_content=False and unindexed.
    if not juans and preface_lines:
        text = "\n".join(preface_lines).strip()
        clean, anchors, line_anchors = _clean_anchors(text)
        if clean:
            juans.append({
                "juan_num": 1,
                "content": clean,
                "char_count": len(clean.replace("\n", "").replace(" ", "")),
                "anchors": anchors,
                "line_anchors": line_anchors,
            })

    return juans


def resolve_xml_path(cbeta_id: str, xml_base_dir: str) -> Path | None:
    """
    Resolve the XML file path for a given CBETA work ID.

    CBETA xml-p5 repository structure:
        xml-p5/{Collection}/{Volume}/{WorkID}.xml
    e.g.:
        xml-p5/T/T01/T01n0001.xml  (for T0001)
        xml-p5/X/X01/X01n0001.xml  (for X0001)
        xml-p5/J/J01/J01nA042.xml  (for JA042)

    Some works span multiple files:
        T01n0001_001.xml, T01n0001_002.xml, ...
    """
    base = Path(xml_base_dir)

    parsed = _parse_cbeta_id(cbeta_id)
    if not parsed:
        return None

    collection, padded_id, suffix = parsed

    collection_dir = base / collection
    if not collection_dir.exists():
        return None

    pattern = f"*n{padded_id}{suffix}.xml"

    for vol_dir in sorted(collection_dir.iterdir()):
        if not vol_dir.is_dir():
            continue
        matches = list(vol_dir.glob(pattern))
        if matches:
            return matches[0]

        multi_pattern = f"*n{padded_id}{suffix}_*.xml"
        multi_matches = sorted(vol_dir.glob(multi_pattern))
        if multi_matches:
            return multi_matches[0]

    return None


def _parse_cbeta_id(cbeta_id: str) -> tuple[str, str, str] | None:
    """
    Parse a CBETA work ID into (collection_dir, file_id_part, suffix).

    Standard: T0001 → ('T', '0001', '')
    J series: JA042 → ('J', 'A042', ''), JB127 → ('J', 'B127', '')
    """
    # J collection special case: JA042, JB127 → dir=J, id_part=A042, B127
    m = re.match(r"^J([AB])(\d+)([a-z]?)$", cbeta_id)
    if m:
        sub = m.group(1)  # A or B
        num_str = m.group(2).zfill(3)
        suffix = m.group(3)
        return ("J", f"{sub}{num_str}", suffix)

    # Standard: T0001, X0001, etc.
    m = re.match(r"^([A-Z]+)(\d+)([a-z]?)$", cbeta_id)
    if m:
        return (m.group(1), m.group(2).zfill(4), m.group(3))

    return None


def find_all_xml_files(cbeta_id: str, xml_base_dir: str) -> list[Path]:
    """Find all XML files for a work (handles multi-file works)."""
    base = Path(xml_base_dir)

    parsed = _parse_cbeta_id(cbeta_id)
    if not parsed:
        return []

    collection, padded_id, suffix = parsed

    collection_dir = base / collection
    if not collection_dir.exists():
        return []

    all_files = []
    for vol_dir in sorted(collection_dir.iterdir()):
        if not vol_dir.is_dir():
            continue

        # Single file
        pattern = f"*n{padded_id}{suffix}.xml"
        all_files.extend(vol_dir.glob(pattern))

        # Multi-file
        multi_pattern = f"*n{padded_id}{suffix}_*.xml"
        all_files.extend(vol_dir.glob(multi_pattern))

    return sorted(set(all_files))


# --------------------------------------------------------------------------
# Critical apparatus (校勘异文) — standoff <app> parsing
# --------------------------------------------------------------------------

def parse_witnesses(root) -> dict[str, str]:
    """Map witness xml:id → readable siglum, e.g. {"wit1": "【宋】"}.

    Each text declares its own witness list, so sigla MUST be resolved per-file;
    the same xml:id means different canons in different texts.
    """
    out: dict[str, str] = {}
    for w in root.findall(f".//{{{TEI_NS}}}witness"):
        wid = w.get(XML_ID)
        if wid:
            out[wid] = "".join(w.itertext()).strip()
    return out


def parse_resp(root) -> dict[str, str]:
    """Map respStmt xml:id → corrector name, e.g. {"resp2": "Taisho"}."""
    out: dict[str, str] = {}
    for rs in root.findall(f".//{{{TEI_NS}}}respStmt"):
        rid = rs.get(XML_ID)
        if not rid:
            continue
        name = rs.find(f"{{{TEI_NS}}}name")
        out[rid] = (name.text or "").strip() if name is not None else ""
    return out


def _sigla(wit_attr: str | None, witnesses: dict[str, str]) -> list[str]:
    """Resolve a space-separated wit="#wit1 #wit2" attribute to sigla."""
    sigla = []
    for ref in (wit_attr or "").split():
        wid = ref.lstrip("#")
        sigla.append(witnesses.get(wid, wid))
    return sigla


def parse_apparatus(root, witnesses: dict[str, str], resps: dict[str, str]) -> list[dict]:
    """Parse all standoff <app> entries (in <back>) into structured dicts.

    Each entry: {app_n, from, to, lemma, lemma_siglum, readings:[...]}.
    A reading: {reading, witnesses:[siglum], resp, is_omission}.
    """
    apps: list[dict] = []
    for app in root.findall(f".//{{{TEI_NS}}}app"):
        frm = (app.get("from") or "").lstrip("#")
        to = (app.get("to") or "").lstrip("#")
        lem = app.find(f"{{{TEI_NS}}}lem")
        if lem is None:
            continue
        lemma = _extract_reading_text(lem).strip()
        lem_sigla = _sigla(lem.get("wit"), witnesses)
        readings: list[dict] = []
        for rdg in app.findall(f"{{{TEI_NS}}}rdg"):
            reading = _extract_reading_text(rdg).strip()
            # <space/> with no text content marks an omission in that witness.
            is_omission = rdg.find(f"{{{TEI_NS}}}space") is not None and not reading
            resp_ids = (rdg.get("resp") or "").split()
            resp = resps.get(resp_ids[0].lstrip("#"), "") if resp_ids else ""
            readings.append({
                "reading": reading,
                "witnesses": _sigla(rdg.get("wit"), witnesses),
                "resp": resp,
                "is_omission": is_omission,
            })
        app_n = frm[3:] if frm.startswith("beg") else frm  # beg0001004 → 0001004
        apps.append({
            "app_n": app_n,
            "from": frm,
            "to": to,
            "lemma": lemma,
            "lemma_siglum": lem_sigla[0] if lem_sigla else "",
            "readings": readings,
        })
    return apps


def parse_tei_apparatus(xml_path: str | Path) -> dict:
    """Parse a CBETA file's critical apparatus, resolved to content offsets.

    Returns {"witnesses": {id: siglum}, "entries": [...]}, where each entry is
    {app_n, juan_num, char_start, char_end, lemma, lemma_siglum, aligned,
    readings}. `aligned` is True iff content[char_start:char_end] == lemma —
    the offsets are computed against the same body parse import_content stores,
    so an unaligned entry (cross-juan span, anchor inside a skipped tag, …) is
    flagged rather than silently mispositioned.
    """
    xml_path = Path(xml_path)
    if not xml_path.exists():
        return {"witnesses": {}, "entries": []}
    try:
        tree = etree.parse(str(xml_path))
    except etree.XMLSyntaxError:
        return {"witnesses": {}, "entries": []}
    root = tree.getroot()

    witnesses = parse_witnesses(root)
    resps = parse_resp(root)
    apps = parse_apparatus(root, witnesses, resps)

    # Map every anchor id → (juan_num, offset) from the body parse.
    juans = parse_tei_xml(xml_path)
    contents: dict[int, str] = {}
    anchor_loc: dict[str, tuple[int, int]] = {}
    line_anchors: list[dict] = []
    for j in juans:
        contents[j["juan_num"]] = j["content"]
        for aid, off in j.get("anchors", {}).items():
            anchor_loc[aid] = (j["juan_num"], off)
        for la in j.get("line_anchors", []):
            line_anchors.append({"juan_num": j["juan_num"], "offset": la["offset"], "line": la["line"]})

    entries: list[dict] = []
    for app in apps:
        loc_f = anchor_loc.get(app["from"])
        loc_t = anchor_loc.get(app["to"])
        if not loc_f or not loc_t or loc_f[0] != loc_t[0]:
            # Anchor missing or span crosses a juan boundary — keep the variant
            # but mark it unaligned (no resolvable position in stored content).
            entries.append({
                "app_n": app["app_n"],
                "juan_num": loc_f[0] if loc_f else (loc_t[0] if loc_t else None),
                "char_start": None,
                "char_end": None,
                "lemma": app["lemma"],
                "lemma_siglum": app["lemma_siglum"],
                "aligned": False,
                "readings": app["readings"],
            })
            continue
        juan_num, start = loc_f
        _, end = loc_t
        # The span may contain "\n" the parser inserted at line/paragraph
        # boundaries; the lemma text does not. Offsets are still correct, so
        # compare with whitespace stripped.
        span = contents.get(juan_num, "")[start:end]
        # Empty lemma would "align" to any whitespace-only span — require a
        # non-empty lemma so a malformed <lem> is flagged, not falsely matched.
        aligned = bool(app["lemma"]) and span.replace("\n", "").replace(" ", "") == app["lemma"]
        entries.append({
            "app_n": app["app_n"],
            "juan_num": juan_num,
            "char_start": start,
            "char_end": end,
            "lemma": app["lemma"],
            "lemma_siglum": app["lemma_siglum"],
            "aligned": aligned,
            "readings": app["readings"],
        })
    return {"witnesses": witnesses, "entries": entries, "line_anchors": line_anchors}
