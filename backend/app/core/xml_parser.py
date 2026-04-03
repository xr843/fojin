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

# Elements whose text content we want to extract (leaf content elements)
CONTENT_TAGS = {
    f"{{{TEI_NS}}}p",
    f"{{{TEI_NS}}}l",       # verse line
    f"{{{TEI_NS}}}head",
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
        else:
            parts.append(_extract_text(child))
            if child.tail:
                parts.append(child.tail)

    return "".join(parts)


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

    def flush_juan():
        nonlocal current_lines
        # Keep blank lines (paragraph boundaries) but strip leading/trailing empties
        text = "\n".join(current_lines)
        text = text.strip()
        if text:
            juans.append({
                "juan_num": current_juan,
                "content": text,
                "char_count": len(text.replace("\n", "").replace(" ", "")),
            })
        current_lines = []

    def process_element(elem):
        nonlocal current_juan, current_lines

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
        if text:
            juans.append({
                "juan_num": 1,
                "content": text,
                "char_count": len(text.replace("\n", "").replace(" ", "")),
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
