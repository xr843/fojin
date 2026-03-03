"""
Parser for GRETIL (Göttingen Register of Electronic Texts in Indian Languages) text files.

GRETIL texts are typically plain text or simple markup files with header metadata.
"""

import re


def parse_gretil_header(content: str) -> dict:
    """Extract metadata from GRETIL file header.

    GRETIL files often have header lines like:
        ## Title: Vajracchedikā Prajñāpāramitā
        ## Author: unknown
        ## Input by: ...
    """
    metadata = {
        "title": "",
        "author": "",
        "input_by": "",
        "source": "",
    }

    header_patterns = {
        "title": r"(?:title|titel)\s*[:：]\s*(.+)",
        "author": r"(?:author|verfasser)\s*[:：]\s*(.+)",
        "input_by": r"(?:input\s*by|eingabe)\s*[:：]\s*(.+)",
        "source": r"(?:source|quelle)\s*[:：]\s*(.+)",
    }

    # Check first 50 lines for header
    lines = content.split("\n")[:50]
    for line in lines:
        line_stripped = line.strip().lstrip("#").strip()
        for key, pattern in header_patterns.items():
            m = re.match(pattern, line_stripped, re.IGNORECASE)
            if m:
                metadata[key] = m.group(1).strip()

    # If no title found, try first non-empty line
    if not metadata["title"]:
        for line in lines:
            stripped = line.strip().lstrip("#").strip()
            if stripped and len(stripped) > 3 and not stripped.startswith("//"):
                metadata["title"] = stripped[:200]
                break

    return metadata


def extract_body(content: str) -> str:
    """Extract the main body text from a GRETIL file.

    Removes header comments, encoding markers, and other non-text content.
    """
    lines = content.split("\n")
    body_lines = []
    in_body = False

    for line in lines:
        stripped = line.strip()

        # Skip header lines
        if not in_body:
            # Body starts after header section (usually marked by empty line or dashes)
            if stripped.startswith("---") or stripped.startswith("==="):
                in_body = True
                continue
            # Or after the header metadata
            if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                # Could be body content, start collecting
                in_body = True

        if in_body:
            # Skip pure comment lines
            if stripped.startswith("//"):
                continue
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    # Remove common markup artifacts
    body = re.sub(r'\{[^}]*\}', '', body)  # Remove {comments}
    body = re.sub(r'<[^>]*>', '', body)    # Remove <tags>

    return body


def parse_gretil_file(content: str, filename: str = "") -> dict:
    """Parse a GRETIL text file and return structured data.

    Returns:
        {
            "title": str,
            "author": str,
            "content": str,
            "char_count": int,
            "filename": str,
        }
    """
    metadata = parse_gretil_header(content)
    body = extract_body(content)

    return {
        "title": metadata["title"],
        "author": metadata["author"],
        "content": body,
        "char_count": len(body),
        "filename": filename,
        "source_info": metadata.get("source", ""),
    }
