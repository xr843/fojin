"""Build fojin cross-canon URNs from a stored cbeta_id.

This is a *vendored*, dependency-free copy of the forward builder in the fojin
backend (``backend/app/services/urn.py::build_urn``). The MCP server is a
standalone process that talks to fojin only over HTTP — it deliberately does not
import the backend package (different dependency closure, independently
installable) — so the ~30 lines that turn a ``cbeta_id`` into a portable URN are
duplicated here on purpose. Keep the two in sync; both are covered by
round-trip tests against the same identifier shapes.

Why the MCP server builds URNs itself rather than reading them off the API:
fojin's search / read / alignment endpoints already expose ``cbeta_id`` but not
a ``urn`` field, so constructing it client-side means every tool result carries
a citable identifier today, without waiting on any server change.

URN grammar (mirrors the backend):

    fojin:<scheme>/<work_id>[.<juan>][#<anchor>]

Schemes map to the cbeta_id prefix conventions: T/X → cbeta, SC- → sc,
84K-toh → 84k, GRETIL- → gretil, VRI- → vri.
"""

from __future__ import annotations

import re

# work_id / anchor grammar — identical to the backend parser so a URN this
# module emits always parses back cleanly (the round-trip guarantee).
_WORK_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ANCHOR_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# (cbeta_id prefix, canonical short scheme). Ordered so the more specific
# "84K-toh" is tested before any shorter prefix could match.
_CANON_PREFIX_SCHEMES: tuple[tuple[str, str], ...] = (
    ("84K-toh", "84k"),
    ("GRETIL-", "gretil"),
    ("SC-", "sc"),
    ("VRI-", "vri"),
)


def build_urn(
    cbeta_id: str | None,
    juan: int | None = None,
    anchor: str | None = None,
) -> str | None:
    """Construct a fojin URN from a stored cbeta_id, or ``None`` if it can't
    produce one that round-trips cleanly.

    Never raises: callers attach the result to a tool payload as a best-effort
    citation id, so an un-buildable case must degrade to "no URN" silently.
    """
    if not isinstance(cbeta_id, str) or not cbeta_id:
        return None

    scheme = "cbeta"
    work_id = cbeta_id
    for prefix, prefix_scheme in _CANON_PREFIX_SCHEMES:
        if cbeta_id.startswith(prefix):
            scheme = prefix_scheme
            work_id = cbeta_id[len(prefix):]
            break

    if not work_id or not _WORK_ID_RE.match(work_id):
        return None
    if anchor is not None and not (isinstance(anchor, str) and _ANCHOR_RE.match(anchor)):
        anchor = None

    urn = f"fojin:{scheme}/{work_id}"
    if isinstance(juan, int) and juan >= 1:
        urn += f".{juan}"
    if anchor:
        urn += f"#{anchor}"
    return urn
