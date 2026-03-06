"""
CBETA TEI P5 XML parser.

Parses CBETA XML files and extracts plain text content split by juan (fascicle).
Handles <milestone unit="juan">, <cb:juan>, <p>, <lg>/<l>, <head> elements.
Skips <note>, <app> (critical apparatus) elements.
"""

import re
from pathlib import Path

from lxml import etree

# CBETA TEI namespace
TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"
NSMAP = {"tei": TEI_NS, "cb": CB_NS}

# Elements whose text content we want to extract
CONTENT_TAGS = {
    f"{{{TEI_NS}}}p",
    f"{{{TEI_NS}}}l",       # verse line
    f"{{{TEI_NS}}}head",
    f"{{{CB_NS}}}div",
}

# Elements to skip entirely (including their children)
SKIP_TAGS = {
    f"{{{TEI_NS}}}note",
    f"{{{TEI_NS}}}app",
    f"{{{TEI_NS}}}rdg",
    f"{{{TEI_NS}}}ref",
    f"{{{CB_NS}}}tt",       # translation table
}


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
        text = "\n".join(line for line in current_lines if line.strip())
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
                flush_juan()
                n = elem.get("n", "")
                try:
                    current_juan = int(n)
                except ValueError:
                    current_juan += 1
            return

        # Skip certain elements
        if tag in SKIP_TAGS:
            return

        # Extract text from content elements
        if tag in CONTENT_TAGS:
            text = _extract_text(elem).strip()
            if text:
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

    Some works span multiple files:
        T01n0001_001.xml, T01n0001_002.xml, ...
    """
    base = Path(xml_base_dir)

    # Extract collection letter and numeric part
    match = re.match(r"^([A-Z]+)(\d+)([a-z]?)$", cbeta_id)
    if not match:
        return None

    collection = match.group(1)
    num_str = match.group(2)
    suffix = match.group(3)

    # Determine volume number from the work number
    num = int(num_str)

    # Search for the file in the collection directory
    collection_dir = base / collection
    if not collection_dir.exists():
        return None

    # Try to find matching XML files
    # Pattern: {Vol}n{Num}.xml or {Vol}n{Num}_001.xml
    padded_num = num_str.zfill(4)
    pattern = f"*n{padded_num}{suffix}.xml"

    for vol_dir in sorted(collection_dir.iterdir()):
        if not vol_dir.is_dir():
            continue
        matches = list(vol_dir.glob(pattern))
        if matches:
            return matches[0]

        # Also try multi-file pattern
        multi_pattern = f"*n{padded_num}{suffix}_*.xml"
        multi_matches = sorted(vol_dir.glob(multi_pattern))
        if multi_matches:
            return multi_matches[0]  # Return first file; caller handles multi-file

    return None


def find_all_xml_files(cbeta_id: str, xml_base_dir: str) -> list[Path]:
    """Find all XML files for a work (handles multi-file works)."""
    base = Path(xml_base_dir)

    match = re.match(r"^([A-Z]+)(\d+)([a-z]?)$", cbeta_id)
    if not match:
        return []

    collection = match.group(1)
    num_str = match.group(2)
    suffix = match.group(3)
    padded_num = num_str.zfill(4)

    collection_dir = base / collection
    if not collection_dir.exists():
        return []

    all_files = []
    for vol_dir in sorted(collection_dir.iterdir()):
        if not vol_dir.is_dir():
            continue

        # Single file
        pattern = f"*n{padded_num}{suffix}.xml"
        all_files.extend(vol_dir.glob(pattern))

        # Multi-file
        multi_pattern = f"*n{padded_num}{suffix}_*.xml"
        all_files.extend(vol_dir.glob(multi_pattern))

    return sorted(set(all_files))
