"""Taishō → Goryeo (Tripitaka Koreana / 高麗大藏經) cross-reference.

Maps a Taishō text id (e.g. T1579) to its Goryeo K-number (K0570) and the
KABC (Dongguk University 불교기록문화유산 아카이브) reader URL for that text's
Goryeo edition. Source: Lancaster, *The Korean Buddhist Canon: A Descriptive
Catalogue* — Taishō index (A. C. Muller), 1,481 mappings, parsed into
data/taisho_goryeo_map.json. Work-level only (no page-level concordance, which
CBETA does not publish).
"""

import json
from pathlib import Path

_MAP_PATH = Path(__file__).parent.parent / "data" / "taisho_goryeo_map.json"
_T2K: dict[str, str] = {}
_LOADED = False

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


def goryeo_k(cbeta_id: str) -> str | None:
    """Goryeo K-number for a Taishō text id, or None if it has no Goryeo parallel."""
    _load()
    return _T2K.get(cbeta_id)


def kabc_url(cbeta_id: str) -> str | None:
    """KABC reader URL for the Goryeo edition of a Taishō text, or None."""
    k = goryeo_k(cbeta_id)
    return f"{KABC_BASE}{k}" if k else None
