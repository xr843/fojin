"""
Parser for GRETIL (Göttingen Register of Electronic Texts in Indian Languages) text files.

GRETIL texts are typically HTML files (.htm) with a standard boilerplate structure,
or plain text files with header metadata.
"""

import re


def _is_html(content: str) -> bool:
    """Check whether the content looks like an HTML document."""
    return bool(re.search(r"<!DOCTYPE\s+html|<html", content[:500], re.IGNORECASE))


def _parse_html(content: str) -> dict:
    """Parse a GRETIL HTML file.

    Standard structure:
        <title> Author: Title </title>
        <head>...<style>...</style>...</head>
        <body>
          metadata lines (author, title, input by, source)
          <hr> ... GRETIL boilerplate / encoding table ... <hr>
          actual Sanskrit text using <BR> as line breaks
        </body>
    """
    # --- title ---
    m = re.search(r"<title[^>]*>\s*(.+?)\s*</title>", content, re.IGNORECASE | re.DOTALL)
    title = m.group(1).strip() if m else ""

    # --- extract body element ---
    m_body = re.search(r"<body[^>]*>(.*)</body>", content, re.IGNORECASE | re.DOTALL)
    body_html = m_body.group(1) if m_body else content

    # --- remove everything up to and including the second <hr> (boilerplate) ---
    # The first <hr> starts the boilerplate notice, the second <hr> ends it.
    parts = re.split(r"<hr\s*/?>", body_html, flags=re.IGNORECASE)
    if len(parts) >= 3:
        # Content is after the second <hr>
        body_html = "<hr>".join(parts[2:])
    elif len(parts) == 2:
        # Only one <hr>, content is after it
        body_html = parts[1]

    # --- strip remaining HTML tags, convert <BR> to newlines ---
    body_html = re.sub(r"<br\s*/?>", "\n", body_html, flags=re.IGNORECASE)
    body_html = re.sub(r"<p\s*/?>", "\n", body_html, flags=re.IGNORECASE)
    body_text = re.sub(r"<[^>]+>", "", body_html)

    # --- clean up whitespace ---
    body_text = re.sub(r"[ \t]+", " ", body_text)
    # Collapse runs of blank lines into at most two newlines
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)
    body_text = body_text.strip()

    # --- author from title (common format: "Author: Title") ---
    author = ""
    if ":" in title:
        author = title.split(":")[0].strip()

    return {
        "title": title,
        "author": author,
        "content": body_text,
    }


def parse_gretil_header(content: str) -> dict:
    """Extract metadata from GRETIL plain-text file header.

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
    """Extract the main body text from a GRETIL plain-text file.

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

    Handles both HTML (.htm) and plain-text formats.

    Returns:
        {
            "title": str,
            "author": str,
            "content": str,
            "char_count": int,
            "filename": str,
        }
    """
    if _is_html(content):
        parsed = _parse_html(content)
        return {
            "title": parsed["title"],
            "author": parsed["author"],
            "content": parsed["content"],
            "char_count": len(parsed["content"]),
            "filename": filename,
            "source_info": "",
        }

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
