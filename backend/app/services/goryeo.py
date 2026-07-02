"""Taishō → Goryeo (Tripitaka Koreana / 高麗大藏經) cross-reference.

Maps a Taishō text id (e.g. T1579) to its Goryeo K-number (K0570) and the
KABC (Dongguk University 불교기록문화유산 아카이브) reader URL for that text's
Goryeo edition. Source: Lancaster, *The Korean Buddhist Canon: A Descriptive
Catalogue* — Taishō index (A. C. Muller), 1,481 mappings, parsed into
data/taisho_goryeo_map.json. Work-level only (no page-level concordance, which
CBETA does not publish).
"""

import json
import re
from pathlib import Path

_MAP_PATH = Path(__file__).parent.parent / "data" / "taisho_goryeo_map.json"
_T2K: dict[str, str] = {}
_LOADED = False

# A trailing letter on a Taishō id (T0235b, T0236a) marks a different
# 见证/edition of the SAME work; the work's Goryeo edition is the base id's K.
_WITNESS_SUFFIX_RE = re.compile(r"[a-z]+$")

KABC_BASE = "https://kabc.dongguk.edu/content/view?dataId=ABC_IT_"


def _load() -> None:
    global _T2K, _LOADED
    if _LOADED:
        return
    try:
        _T2K = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        _T2K = {}
    _LOADED = True


def goryeo_k(cbeta_id: str | None) -> str | None:
    """Goryeo K-number for a Taishō text id, or None if it has no Goryeo parallel.

    Exact match wins — some witness variants (T0150a/b) are mapped to their OWN
    distinct K-numbers and must not be collapsed. Only on an exact miss do we
    retry with the witness-suffix stripped, so a record like T0235b resolves to
    its base work's Goryeo edition (the 高丽藏 button means "view this work in
    the Goryeo canon"). Without this, the button silently vanished on every
    suffix-variant record whose exact id wasn't separately catalogued.
    """
    _load()
    if not cbeta_id:
        return None
    k = _T2K.get(cbeta_id)
    if k is not None:
        return k
    base = _WITNESS_SUFFIX_RE.sub("", cbeta_id)
    return _T2K.get(base) if base != cbeta_id else None


def kabc_url(cbeta_id: str | None) -> str | None:
    """KABC reader URL for the Goryeo edition of a Taishō text, or None."""
    k = goryeo_k(cbeta_id)
    return f"{KABC_BASE}{k}" if k else None
