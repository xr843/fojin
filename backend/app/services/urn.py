"""URN parser and resolver for fojin's stable text references.

fojin does not invent its own canonical identifier scheme — CBETA's
``T0001`` style is the de-facto standard in Chinese Buddhist
philology. The URN form below is a thin wrap that gives external
citations a single grammatical shape they can paste into a paper or
embed in an external dataset, with deterministic resolution to a
reader URL.

URN grammar (BNF-ish):

    URN       := "fojin:" SCHEME "/" PATH ["#" ANCHOR]
    SCHEME    := "cbeta"                       # extensible; only CBETA today
    PATH      := WORK ["." JUAN]
    WORK      := <cbeta_id as stored, e.g. T0001, X0123, SC-mn10>
    JUAN      := <positive integer>
    ANCHOR    := <opaque token passed to reader as ?anchor=>

Examples:

    fojin:cbeta/T0001                  → text-level: redirect to /text/{id}
    fojin:cbeta/T0001.1                → juan-level: redirect to /reader?text=&juan=1
    fojin:cbeta/T0001.1#p0001a01       → line-level: same + ?anchor=p0001a01

The ANCHOR is intentionally opaque: this PR does not index CBETA's
``<lb n="...">`` line numbers; instead anchors flow through to the
reader as a fragment hint that future PRs (or external tools) can
consume. Treating the anchor as opaque means the URN scheme survives
the eventual index-time work without a URI version bump.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.text import get_text_id_by_cbeta

logger = logging.getLogger(__name__)


# Restrict to the schemes we currently understand. Unknown schemes
# are an error, not a silent fall-through — we'd rather break loudly
# than redirect to a wrong place.
_KNOWN_SCHEMES = frozenset({"cbeta"})

# The path body before # / before the optional ".juan" suffix. CBETA
# IDs in the wild use [A-Za-z0-9-]; we allow that plus underscore for
# future-proofing without opening the door to path traversal.
_WORK_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ANCHOR_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class ParsedURN:
    """Structured form of a fojin URN.

    juan and anchor are None when the URN does not specify them; a
    text-level URN is fully valid and resolves to the text detail page.
    """

    raw: str
    scheme: str
    work_id: str
    juan: int | None
    anchor: str | None


class URNParseError(ValueError):
    """The input string is not a syntactically valid fojin URN."""


def parse_urn(urn: str) -> ParsedURN:
    """Parse a fojin URN string into its structured components.

    Raises URNParseError on malformed input. Does not touch the
    database; resolution to a text id is a separate step.
    """
    if not isinstance(urn, str) or not urn:
        raise URNParseError("urn must be a non-empty string")

    if not urn.startswith("fojin:"):
        raise URNParseError("urn must start with 'fojin:'")

    body = urn[len("fojin:"):]

    # Split off optional #anchor first so a "/" inside the anchor (we
    # don't expect any, but be defensive) doesn't confuse the scheme
    # split.
    if "#" in body:
        body, anchor = body.split("#", 1)
        if not _ANCHOR_RE.match(anchor):
            raise URNParseError(f"invalid anchor: {anchor!r}")
    else:
        anchor = None

    if "/" not in body:
        raise URNParseError("urn must contain 'scheme/path'")
    scheme, path = body.split("/", 1)
    if scheme not in _KNOWN_SCHEMES:
        raise URNParseError(f"unknown scheme: {scheme!r}")

    if "." in path:
        work_id, juan_str = path.split(".", 1)
        try:
            juan = int(juan_str)
            if juan < 1:
                raise ValueError
        except ValueError as exc:
            raise URNParseError(f"invalid juan number: {juan_str!r}") from exc
    else:
        work_id = path
        juan = None

    if not _WORK_ID_RE.match(work_id):
        raise URNParseError(f"invalid work id: {work_id!r}")

    return ParsedURN(
        raw=urn,
        scheme=scheme,
        work_id=work_id,
        juan=juan,
        anchor=anchor,
    )


def build_reader_url(parsed: ParsedURN, *, text_id: int) -> str:
    """Produce the in-app reader URL a resolver should redirect to.

    URLs are relative paths so that they work for both local dev and
    prod fojin.app. The caller (the API endpoint) decides whether to
    return them as-is or compose an absolute URL.
    """
    if parsed.juan is None:
        # Text-level: jump to the detail page so the user picks a juan.
        return f"/texts/{text_id}"
    base = f"/reader?text={text_id}&juan={parsed.juan}"
    if parsed.anchor:
        base += f"&anchor={parsed.anchor}"
    return base


async def resolve_urn(
    db: AsyncSession, parsed: ParsedURN
) -> tuple[int | None, str | None]:
    """Resolve a parsed URN to (text_id, reader_url) or (None, None).

    Returns (None, None) when the referenced work is not in the
    database — letting the API layer respond with 404 instead of
    redirecting to a nonexistent page.
    """
    if parsed.scheme != "cbeta":
        # Future schemes route here; today's URN parser already
        # rejects them, so this branch is defense-in-depth.
        return None, None

    text_id = await get_text_id_by_cbeta(db, parsed.work_id)
    if text_id is None:
        logger.info("urn resolve miss: scheme=%s work=%s", parsed.scheme, parsed.work_id)
        return None, None

    return text_id, build_reader_url(parsed, text_id=text_id)
