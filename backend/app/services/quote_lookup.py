"""Open-world verbatim quote lookup against the full corpus.

The chat-path verifier (``quote_verifier.py``) is *closed-world*: it tests a
quote against the chunks retrieved for one conversation. This service answers
the open question — "does this quote exist verbatim anywhere in the canon?" —
for the public ``/api/verify/quote`` endpoint and the hosted MCP tool.

Design contract (keep these invariants):

- **ES shortlists, Postgres decides.** The ES ``text_contents`` index
  (analyzer ``cjk_content`` ≈ ``normalise_for_match``) is used only to find
  candidate fascicles. The authoritative verbatim decision is always the
  normalised substring test against the source text — so "verbatim" has one
  definition system-wide (the chat verifier's).
- **No silent juan fallback.** When the caller hints a juan, a hit in a
  different juan is reported with ``juan_matched=False`` instead of being
  passed off as confirmation (the chat pipeline's any-juan fallback is a
  known fascicle-accuracy leak; the public API must not inherit it).
- **lzh only, gaiji not folded** in v1 — both stated in ``caveats`` so the
  verdict is honest about its blind spots.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from elasticsearch import AsyncElasticsearch
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.verification import ClosestMiss, DiffOp, QuoteMatch, QuoteVerdict
from app.services.quote_verifier import (
    MIN_QUOTE_CHARS,
    NEAR_MISS_THRESHOLD,
    normalise_for_match,
)
from app.services.urn import (
    absolute_reader_url,
    build_urn,
    parse_urn,
    reader_path,
    resolve_urn,
)

logger = logging.getLogger(__name__)

# How many ES phrase candidates we confirm against Postgres.
_MAX_CANDIDATES = 5
# Fuzzy fallback candidates when the phrase query finds nothing.
_MAX_FUZZY_CANDIDATES = 3
# Full-text-scan ceiling: scanning every juan of a hinted text is allowed
# only under this fascicle count (T0220 has 600 juans of ~100k chars — a
# blind full scan there is a several-hundred-MB read).
_MAX_FULL_SCAN_JUANS = 60
# Same window cap as quote_verifier._windowed_ratio.
_MAX_RATIO_WINDOWS = 256

# The chat verifier requires 12 characters because it extracts quoted spans
# from prose and must not mistake a 「」-marked emphasis for a citation. Here
# the caller states outright that the string is a quotation, and the phrases
# people most need checked are short — 應無所住而生其心 is 8, 色即是空 is 4.
# Refusing them made the endpoint useless for its most common question. The
# floor stays at one 四字句, the smallest unit that means anything in
# Classical Chinese; below that the answer would be noise either way.
MIN_LOOKUP_QUOTE_CHARS = 4

_CAVEATS = [
    "lzh (Classical Chinese) corpus only; Pali/Tibetan/Sanskrit parallels are not searched.",
    "CBETA gaiji variant characters are not folded yet; a quote using a common "
    "variant form may miss a source encoded with a composition expression.",
]

# Added for quotes below the chat verifier's threshold, where "it exists"
# stops being informative on its own.
_SHORT_QUOTE_CAVEAT = (
    "This quote is short, and short phrases recur across the canon: verbatim "
    "presence alone is weak evidence of a source. Treat cite_matched — whether "
    "it is where the citation claims — as the answer that carries information, "
    "and note that matches may be capped (see matches_capped)."
)

# Loose shape check for a bare cbeta-style work id (T0374, X0600, SC-mn10,
# 84K-toh123…). Resolution against buddhist_texts is the real validator.
_CBETA_HINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{0,30}$")


class QuoteTooShortError(ValueError):
    """Raised when the quote normalises to fewer than MIN_QUOTE_CHARS chars."""


@dataclass(frozen=True)
class _CiteTarget:
    text_id: int
    cbeta_id: str | None
    title_zh: str | None
    juan: int | None


def _anchor_starts(needle: str, haystack: str, nlen: int) -> list[int]:
    """Window starts guessed by finding an exact run of the quote in the source.

    The scan below steps by ``nlen // 4`` and is then subsampled to at most
    ``_MAX_RATIO_WINDOWS``, so over a 100k-character fascicle it only lands
    every few hundred characters — enough to score a near-miss, far too coarse
    to frame it. A near-miss almost always shares a long verbatim run with its
    source, so a plain ``str.find`` of a slice of the quote locates the true
    offset in O(n) and lets the window be cut where a reader would cut it.
    Best-effort: any miss just leaves the coarse scan's answer standing.
    """
    starts: list[int] = []
    for probe_len in (nlen // 2, nlen // 4, 8):
        # A probe longer than the needle would slice from a negative offset
        # and anchor on nonsense — reachable now that short quotes are allowed.
        if probe_len < 4 or probe_len > nlen:
            continue
        offset = (nlen - probe_len) // 2
        pos = haystack.find(needle[offset : offset + probe_len])
        if pos != -1:
            starts.append(max(0, min(pos - offset, len(haystack) - nlen)))
    return starts


def windowed_best_span(needle: str, haystack: str) -> tuple[float, int, int]:
    """Best SequenceMatcher ratio of ``needle`` against any same-length window
    of ``haystack``, plus that window's [start, end) span.

    Uses ``quote_verifier._windowed_ratio``'s scan (coarse step, capped window
    count, tail always included) and additionally tries anchor-derived starts,
    so the reported window is framed on the match rather than merely near it —
    which is what makes the character-level diff readable.

    That extra candidate means this can score a window the chat-path function
    misses, so its ratio is ``>=`` that one, never ``<``. The chat path is
    deliberately left alone: its numbers are the baseline the faithfulness
    metrics are tracked against, and improving them silently would break the
    comparison. Inputs must already be normalised.
    """
    if not needle or not haystack:
        return 0.0, 0, 0
    nlen = len(needle)
    if len(haystack) <= nlen:
        return (
            SequenceMatcher(None, needle, haystack, autojunk=False).ratio(),
            0,
            len(haystack),
        )
    step = max(1, nlen // 4)
    starts = list(range(0, len(haystack) - nlen + 1, step))
    tail = len(haystack) - nlen
    if starts[-1] != tail:
        starts.append(tail)
    if len(starts) > _MAX_RATIO_WINDOWS:
        stride = len(starts) / _MAX_RATIO_WINDOWS
        starts = [starts[int(i * stride)] for i in range(_MAX_RATIO_WINDOWS)]
    starts.extend(_anchor_starts(needle, haystack, nlen))
    best, best_start = 0.0, 0
    for s in starts:
        r = SequenceMatcher(None, needle, haystack[s : s + nlen], autojunk=False).ratio()
        if r > best:
            best, best_start = r, s
            if best >= 0.999:
                break
    return best, best_start, best_start + nlen


def diff_ops(quote: str, window: str) -> list[DiffOp]:
    """Character-level differences between the quote and the source window.

    Both inputs are already normalised, and the result stays in that space —
    see ``DiffOp``. Inputs are bounded by the endpoint's 400-character limit
    on ``q``, so the op list is short enough to return whole; nothing is
    truncated, because a silently shortened diff is worse than none.
    """
    if not quote or not window:
        return []
    ops: list[DiffOp] = []
    matcher = SequenceMatcher(None, quote, window, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        ops.append(DiffOp(op=tag, quote=quote[i1:i2], source=window[j1:j2]))
    return ops


async def _resolve_cite(
    db: AsyncSession, cite: str, juan: int | None
) -> _CiteTarget | None:
    """Resolve a cite hint (bare cbeta id or fojin URN) to a text target.

    A juan inside a URN wins over the separate ``juan`` param only when the
    latter is absent — an explicit param is the more deliberate signal.
    """
    cite = cite.strip()
    text_id: int | None = None
    urn_juan: int | None = None
    if cite.lower().startswith("fojin:"):
        try:
            parsed = parse_urn(cite)
        except ValueError:
            return None
        urn_juan = parsed.juan
        text_id, _ = await resolve_urn(db, parsed)
    elif _CBETA_HINT_RE.match(cite):
        row = (
            await db.execute(
                sql_text(
                    "SELECT id FROM buddhist_texts WHERE cbeta_id = :c "
                    "ORDER BY id ASC LIMIT 1"
                ),
                {"c": cite},
            )
        ).fetchone()
        text_id = row[0] if row else None
    if text_id is None:
        return None
    meta = (
        await db.execute(
            sql_text("SELECT cbeta_id, title_zh FROM buddhist_texts WHERE id = :t"),
            {"t": text_id},
        )
    ).fetchone()
    return _CiteTarget(
        text_id=text_id,
        cbeta_id=meta[0] if meta else None,
        title_zh=meta[1] if meta else None,
        juan=juan if juan is not None else urn_juan,
    )


async def _fetch_juan(db: AsyncSession, text_id: int, juan_num: int) -> str | None:
    row = (
        await db.execute(
            sql_text(
                "SELECT content FROM text_contents "
                "WHERE text_id = :t AND juan_num = :j AND lang = 'lzh' LIMIT 1"
            ),
            {"t": text_id, "j": juan_num},
        )
    ).fetchone()
    return row[0] if row else None


async def _juan_count(db: AsyncSession, text_id: int) -> int:
    row = (
        await db.execute(
            sql_text(
                "SELECT COUNT(*) FROM text_contents "
                "WHERE text_id = :t AND lang = 'lzh'"
            ),
            {"t": text_id},
        )
    ).fetchone()
    return int(row[0]) if row else 0


async def _all_juans(db: AsyncSession, text_id: int) -> list[tuple[int, str]]:
    rows = (
        await db.execute(
            sql_text(
                "SELECT juan_num, content FROM text_contents "
                "WHERE text_id = :t AND lang = 'lzh' ORDER BY juan_num"
            ),
            {"t": text_id},
        )
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


async def _es_candidates(
    es: AsyncElasticsearch,
    quote: str,
    *,
    text_id: int | None,
    phrase: bool,
    size: int,
) -> list[dict]:
    """Candidate fascicles from ES. ``phrase=True`` is the precise pass
    (cjk_content analyzer makes match_phrase ≈ normalised-substring recall);
    ``phrase=False`` is the fuzzy fallback used only to find *closest* text
    for a near-miss verdict."""
    query_type = "match_phrase" if phrase else "match"
    content_query: dict = {
        query_type: {"content": {"query": quote, "analyzer": "cjk_content"}}
    }
    filters: list[dict] = [{"term": {"lang": "lzh"}}]
    if text_id is not None:
        filters.append({"term": {"text_id": text_id}})
    body = {
        "query": {"bool": {"must": [content_query], "filter": filters}},
        "size": size,
        "_source": ["text_id", "cbeta_id", "title_zh", "juan_num"],
    }
    try:
        resp = await es.search(index="text_contents", body=body)
        # elasticsearch-py 8.x returns ObjectApiResponse (Mapping-like, NOT a
        # dict) — subscript it; an isinstance(resp, dict) guard silently
        # discards every real result while passing dict-based test doubles.
        hits = resp["hits"]["hits"]
    except Exception:  # pragma: no cover - ES outage degrades, not crashes
        logger.warning("verify_quote ES candidate search failed", exc_info=True)
        return []
    out = []
    for h in hits:
        src = h.get("_source") or {}
        if isinstance(src.get("text_id"), int) and isinstance(src.get("juan_num"), int):
            out.append(src)
    return out


def _match_from(
    src: dict, *, hinted_juan: int | None
) -> QuoteMatch:
    juan_num = src["juan_num"]
    return QuoteMatch(
        text_id=src["text_id"],
        cbeta_id=src.get("cbeta_id"),
        title_zh=src.get("title_zh"),
        juan_num=juan_num,
        urn=build_urn(src.get("cbeta_id"), juan_num),
        reader_url=absolute_reader_url(reader_path(src["text_id"], juan_num)),
        juan_matched=(juan_num == hinted_juan) if hinted_juan is not None else None,
    )


async def verify_quote(
    db: AsyncSession,
    es: AsyncElasticsearch,
    quote: str,
    *,
    cite: str | None = None,
    juan: int | None = None,
) -> QuoteVerdict:
    """Open-world verbatim check of ``quote`` against the corpus."""
    needle = normalise_for_match(quote)
    if len(needle) < MIN_LOOKUP_QUOTE_CHARS:
        raise QuoteTooShortError(
            f"quote must normalise to at least {MIN_LOOKUP_QUOTE_CHARS} chars "
            f"(got {len(needle)})"
        )

    target: _CiteTarget | None = None
    cite_resolved: bool | None = None
    if cite:
        target = await _resolve_cite(db, cite, juan)
        cite_resolved = target is not None

    hinted_juan = target.juan if target else None
    matches: list[QuoteMatch] = []
    best_miss: tuple[float, int, int, str] | None = None  # ratio, text_id, juan, window

    def _note_miss(ratio: float, text_id: int, juan_num: int, window: str) -> None:
        nonlocal best_miss
        if best_miss is None or ratio > best_miss[0]:
            best_miss = (ratio, text_id, juan_num, window)

    async def _confirm(src: dict) -> bool:
        body = await _fetch_juan(db, src["text_id"], src["juan_num"])
        if body is None:
            return False
        norm_body = normalise_for_match(body)
        if needle in norm_body:
            matches.append(_match_from(src, hinted_juan=hinted_juan))
            return True
        ratio, start, end = windowed_best_span(needle, norm_body)
        _note_miss(ratio, src["text_id"], src["juan_num"], norm_body[start:end])
        return False

    if target is not None:
        # Hinted-text paths. Never scan-blind on huge texts.
        base_src = {
            "text_id": target.text_id,
            "cbeta_id": target.cbeta_id,
            "title_zh": target.title_zh,
        }
        if target.juan is not None:
            await _confirm({**base_src, "juan_num": target.juan})
        if not matches:
            # ES narrows within the hinted text (finds hits in other juans —
            # reported honestly as juan_matched=False when a juan was hinted).
            cands = await _es_candidates(
                es, quote, text_id=target.text_id, phrase=True, size=_MAX_CANDIDATES
            )
            for src in cands:
                if src["juan_num"] != target.juan:
                    await _confirm({**base_src, "juan_num": src["juan_num"]})
            # ES found nothing phrase-exact in this text; a bounded full
            # scan catches ES/normalisation drift on small texts.
            if (
                not matches
                and not cands
                and await _juan_count(db, target.text_id) <= _MAX_FULL_SCAN_JUANS
            ):
                for juan_num, body in await _all_juans(db, target.text_id):
                    if juan_num == target.juan:
                        continue  # already tested
                    norm_body = normalise_for_match(body)
                    if needle in norm_body:
                        matches.append(
                            _match_from(
                                {**base_src, "juan_num": juan_num},
                                hinted_juan=hinted_juan,
                            )
                        )
                        if len(matches) >= _MAX_CANDIDATES:
                            break
                    else:
                        ratio, start, end = windowed_best_span(needle, norm_body)
                        _note_miss(ratio, target.text_id, juan_num, norm_body[start:end])

    if not matches:
        # Open-world pass (also runs when a cite hint resolved but missed —
        # "not where you said, but it IS here" is the useful answer).
        for src in await _es_candidates(
            es, quote, text_id=None, phrase=True, size=_MAX_CANDIDATES
        ):
            if len(matches) >= _MAX_CANDIDATES:
                break
            await _confirm(src)

    if not matches and best_miss is None:
        # Nothing phrase-exact anywhere: fuzzy fallback purely to locate the
        # closest text for the near_miss/absent verdict.
        for src in await _es_candidates(
            es, quote, text_id=None, phrase=False, size=_MAX_FUZZY_CANDIDATES
        ):
            await _confirm(src)

    verbatim = bool(matches)
    if verbatim:
        bucket, similarity, closest = "exact", 1.0, None
    else:
        similarity = best_miss[0] if best_miss else 0.0
        bucket = "near_miss" if similarity >= NEAR_MISS_THRESHOLD else "absent"
        closest = None
        if best_miss:
            ratio, text_id, juan_num, window = best_miss
            meta = (
                await db.execute(
                    sql_text("SELECT cbeta_id FROM buddhist_texts WHERE id = :t"),
                    {"t": text_id},
                )
            ).fetchone()
            closest = ClosestMiss(
                text_id=text_id,
                juan_num=juan_num,
                urn=build_urn(meta[0] if meta else None, juan_num),
                reader_url=absolute_reader_url(reader_path(text_id, juan_num)),
                similarity=round(ratio, 4),
                window_normalised=window,
                diff=diff_ops(needle, window),
            )

    cite_matched: bool | None = None
    if cite:
        if target is None:
            cite_matched = False
        elif hinted_juan is not None:
            cite_matched = any(
                m.text_id == target.text_id and m.juan_num == hinted_juan
                for m in matches
            )
        else:
            cite_matched = any(m.text_id == target.text_id for m in matches)

    caveats = list(_CAVEATS)
    if len(needle) < MIN_QUOTE_CHARS:
        caveats.insert(0, _SHORT_QUOTE_CAVEAT)

    return QuoteVerdict(
        quote=quote,
        normalised_quote=needle,
        verbatim=verbatim,
        bucket=bucket,
        similarity=round(similarity, 4) if not verbatim else 1.0,
        matches=matches,
        matches_capped=len(matches) >= _MAX_CANDIDATES,
        closest=closest,
        cite_resolved=cite_resolved,
        cite_matched=cite_matched,
        caveats=caveats,
    )
