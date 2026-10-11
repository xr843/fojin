"""Which part of the canon a CBETA text belongs to — and what that means for
the question「这句话是佛说的吗？」.

The Taishō numbering is itself the canon's order: Āgamas, Jātaka, Prajñā,
Lotus, Avataṃsaka, Ratnakūṭa, Nirvāṇa, Mahāsaṃnipāta, sūtra collection,
esoteric sūtras, then vinaya, treatises, commentaries, school writings,
histories and catalogues. Sorting candidate sources by that number therefore
puts the earliest, closest-to-scripture source first — which BM25 does not:
commentaries quote a famous line many times and outscore the sūtra itself
(measured 2026-10-11: the primary source ranked first for 1/25 famous quotes).
See docs/superpowers/specs/2026-10-11-verify-page-design.md §3.
"""

import re
from typing import Literal

CanonClass = Literal[
    "sutra", "vinaya", "treatise", "commentary", "school", "history", "apocrypha", "later", "unknown"
]

# (first, last, class) over Taishō numbers, inclusive.
_TAISHO_RANGES: tuple[tuple[int, int, CanonClass], ...] = (
    (1, 1420, "sutra"),  # 阿含 … 經集 + 密教
    (1421, 1504, "vinaya"),  # 律部
    (1505, 1692, "treatise"),  # 釋經論 毘曇 中觀 瑜伽 論集
    (1693, 1850, "commentary"),  # 經疏 律疏 論疏
    (1851, 2025, "school"),  # 諸宗部（含《六祖壇經》T2008）
    (2026, 2184, "history"),  # 史傳 事彙 外教 目錄
    (2732, 2864, "later"),  # 古逸部（敦煌寫本，多為注疏）
    (2865, 2920, "apocrypha"),  # 疑似部
)

_ID_RE = re.compile(r"^([A-Z]+)(\d+)")

# Painless sort key mirroring canon_order_key(): Taishō by number, then the
# Chinese translation of the Pali canon (N), then the Xuzangjing (X), then any
# other collection. Executed by Elasticsearch on the keyword doc value.
CANON_ORDER_SCRIPT = """
if (doc['cbeta_id'].size() == 0) { return 9.0E9; }
String id = doc['cbeta_id'].value;
int i = 0;
while (i < id.length() && Character.isLetter(id.charAt(i))) { i++; }
if (i == 0 || i == id.length()) { return 9.0E9; }
String prefix = id.substring(0, i);
long n = 0;
int j = i;
while (j < id.length() && Character.isDigit(id.charAt(j))) { n = n * 10 + (id.charAt(j) - (char)'0'); j++; }
double base = prefix == 'T' ? 0 : (prefix == 'N' ? 50000 : (prefix == 'X' ? 100000 : 200000));
return base + n;
"""


def _parse(cbeta_id: str | None) -> tuple[str, int] | None:
    m = _ID_RE.match(cbeta_id or "")
    if not m:
        return None
    return m.group(1), int(m.group(2))


def canon_order_key(cbeta_id: str | None) -> float:
    """Python twin of CANON_ORDER_SCRIPT (used to re-sort confirmed matches)."""
    parsed = _parse(cbeta_id)
    if parsed is None:
        return 9.0e9
    prefix, n = parsed
    base = {"T": 0, "N": 50_000, "X": 100_000}.get(prefix, 200_000)
    return base + n


def canon_class(cbeta_id: str | None) -> CanonClass:
    parsed = _parse(cbeta_id)
    if parsed is None:
        return "unknown"
    prefix, n = parsed
    if prefix == "T":
        for first, last, cls in _TAISHO_RANGES:
            if first <= n <= last:
                return cls
        return "unknown"
    if prefix == "N":  # 漢譯南傳大藏經
        return "sutra"
    return "later"  # 卍續藏 X、嘉興藏 J 等：後世注疏、語錄、儀軌
