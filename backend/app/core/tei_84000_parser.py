"""
Parser for 84000 TEI XML translation files.

84000's translations are published as TEI XML documents with structure:
  <TEI xmlns="http://www.tei-c.org/ns/1.0">
    <teiHeader>
      <fileDesc>
        <titleStmt>
          <title type="mainTitle" xml:lang="en">...</title>
          <title type="mainTitle" xml:lang="bo">...</title>
        </titleStmt>
      </fileDesc>
    </teiHeader>
    <text>
      <body>
        <div type="translation">...</div>
      </body>
    </text>
  </TEI>
"""

import re
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring as safe_fromstring

TEI_NS = "http://www.tei-c.org/ns/1.0"


def parse_84000_tei(xml_content: str) -> dict:
    """Parse an 84000 TEI XML file.

    Returns:
        {
            "title_en": str,
            "title_bo": str,
            "title_sa": str,
            "toh_number": str,
            "translation_en": str,
            "translation_bo": str,
            "summary": str,
        }
    """
    result = {
        "title_en": "",
        "title_bo": "",
        "title_sa": "",
        "toh_number": "",
        "translation_en": "",
        "translation_bo": "",
        "summary": "",
    }

    try:
        # Parse XML, handling namespaces
        root = safe_fromstring(xml_content)
    except ET.ParseError:
        # Try to clean up common issues
        cleaned = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;)', '&amp;', xml_content)
        try:
            root = safe_fromstring(cleaned)
        except ET.ParseError:
            return result

    ns = {"tei": TEI_NS}

    # Extract titles
    for title_elem in root.findall(".//tei:titleStmt/tei:title", ns):
        lang = title_elem.get("{http://www.w3.org/XML/1998/namespace}lang", "")
        title_text = "".join(title_elem.itertext()).strip()

        if lang == "en":
            result["title_en"] = title_text
        elif lang == "bo":
            result["title_bo"] = title_text
        elif lang == "Sa-Ltn" or lang == "sa":
            result["title_sa"] = title_text

    # Tohoku number
    for idno in root.findall(".//tei:publicationStmt/tei:idno", ns):
        idno_type = idno.get("type", "")
        if "Toh" in idno_type or "toh" in idno.text if idno.text else False:
            result["toh_number"] = (idno.text or "").strip()

    # Extract translation text
    for div in root.findall(".//tei:body//tei:div", ns):
        div_type = div.get("type", "")
        if div_type == "translation":
            # Get all paragraph text
            paragraphs = []
            for p in div.findall(".//tei:p", ns):
                p_text = "".join(p.itertext()).strip()
                if p_text:
                    paragraphs.append(p_text)
            result["translation_en"] = "\n\n".join(paragraphs)

        elif div_type == "summary":
            summary_parts = []
            for p in div.findall(".//tei:p", ns):
                p_text = "".join(p.itertext()).strip()
                if p_text:
                    summary_parts.append(p_text)
            result["summary"] = "\n".join(summary_parts)

    return result


def extract_toh_number(filename: str) -> str:
    """Extract Tohoku catalog number from filename.

    Examples:
        toh1-1.xml → 1
        toh44.xml → 44
        UT22084-001-001.xml → 1
    """
    m = re.search(r'toh(\d+)', filename, re.IGNORECASE)
    if m:
        return m.group(1)

    m = re.search(r'UT\d+-(\d+)-', filename)
    if m:
        return str(int(m.group(1)))

    return ""
