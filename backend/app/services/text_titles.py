"""Title keys shared by everything that matches a cited 《经名》 to a source.

Long CBETA works are stored split into parts whose ``title_zh`` carries the
fascicle range: 「大般若波羅蜜多經(第401卷-第600卷)」, 「成唯識論證義(第1卷-第3卷)」
(22 works in production, 15 of them the 大般若經). The model — and every
reader — writes the bare title, so an exact comparison misses a work that IS
in the retrieved sources. Measured 2026-11-16: 27 of the 124 「unverified
title」 rewrites in 30 days were exactly this; the guard stripped the clickable
citation of a correct, retrieved source. Fascicle numbers inside those parts
are absolute (卷 403 lives in the 401–600 part), so merging the parts under
one key keeps juan checks correct.
"""

import re

# 「(第401卷-第600卷)」 at the end of a title — ASCII or full-width parens.
_VOLUME_RANGE_RE = re.compile(r"\s*[（(]第[0-9]+卷-第[0-9]+卷[)）]\s*$")


def strip_volume_range(title: str) -> str:
    """「成唯識論證義(第1卷-第3卷)」 → 「成唯識論證義」; other titles unchanged."""
    return _VOLUME_RANGE_RE.sub("", title).strip()
