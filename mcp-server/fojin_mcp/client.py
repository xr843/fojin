"""Async HTTP client over fojin's public read-only API, plus the pure functions
that reshape each endpoint's response into a citation-carrying tool result.

Design: everything here is import-light (httpx only, no ``mcp``) so the reshaping
logic is unit-testable with a mocked transport, independent of the MCP runtime.
``server.py`` is the thin layer that registers these as MCP tools.

Every result that identifies a canonical passage carries a ``urn`` — the whole
point of the server: an AI calling these tools gets back a portable, resolvable
citation (``fojin:cbeta/T0251.1``) it can cite and deep-link, not an opaque
internal id. Read-only: no endpoint here mutates fojin state.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .urn import build_urn

# Cap on per-call text→cbeta_id lookups when enriching parallels with URNs, so a
# pathological juan with many distinct aligned texts can't fan out unboundedly.
_MAX_URN_ENRICH_LOOKUPS = 20

DEFAULT_BASE_URL = "https://fojin.app/api"
DEFAULT_TIMEOUT = 20.0
# fojin is a scholarly public good; identify the client so its traffic is
# attributable and it can be rate-limited/allow-listed distinctly from browsers.
USER_AGENT = "fojin-mcp/0.1 (+https://github.com/xr843/fojin)"


class FojinAPIError(RuntimeError):
    """A fojin API call failed (network, timeout, or non-2xx). The message is
    safe to surface to the calling model as a tool error."""


class FojinClient:
    """Thin async wrapper over the fojin HTTP API.

    One client owns one ``httpx.AsyncClient``; use it as an async context
    manager so the connection pool is closed deterministically. ``base_url``
    defaults to prod but is overridable (env/tests/self-host).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # Injectable client so tests pass a mocked transport; otherwise we own it.
        self._client = client or httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": USER_AGENT}
        )
        self._owns_client = client is None
        # text_id → cbeta_id is static corpus metadata; caching it collapses the
        # 1+N fan-out of repeated get_parallels calls on a long-lived client.
        self._cbeta_cache: dict[int, str] = {}

    async def __aenter__(self) -> FojinClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise FojinAPIError(
                f"fojin API {exc.response.status_code} for {path}"
            ) from exc
        except httpx.HTTPError as exc:
            raise FojinAPIError(f"fojin API request failed for {path}: {exc}") from exc

    # ── tools ────────────────────────────────────────────────────────────

    async def search_corpus(
        self, query: str, limit: int = 10, lang: str | None = None
    ) -> dict[str, Any]:
        """Semantic search across the corpus → citation-carrying hits."""
        params: dict[str, Any] = {"q": query, "size": _clamp(limit, 1, 50)}
        if lang:
            params["lang"] = lang
        data = await self._get("/search/semantic", params)
        return shape_search_results(data)

    async def read_passage(self, text_id: int, juan_num: int) -> dict[str, Any]:
        """Fetch the actual content of one fascicle (卷) with its URN."""
        data = await self._get(f"/texts/{text_id}/juans/{juan_num}")
        return shape_passage(data)

    async def get_parallels(self, text_id: int, juan_num: int) -> dict[str, Any]:
        """Cross-canon aligned parallels for a fascicle (the alignment moat).

        The alignment endpoint returns parallels keyed by internal text_id (no
        cbeta_id), so we enrich each fojin-native parallel with a portable URN by
        resolving its distinct text_ids → cbeta_id in a bounded, concurrent,
        best-effort pass. A lookup miss just leaves that parallel's urn None;
        it never fails the whole call.
        """
        data = await self._get(f"/alignment/texts/{text_id}/juans/{juan_num}")
        shaped = shape_parallels(data)
        await self._enrich_parallel_urns(shaped["parallels"])
        return shaped

    async def _text_cbeta_id(self, text_id: int) -> str | None:
        """Best-effort text_id → cbeta_id via /texts/{id}; None on any failure.

        Successful lookups are cached for the client's lifetime (the mapping is
        static); failures are not, so a transient error can heal on retry."""
        if text_id in self._cbeta_cache:
            return self._cbeta_cache[text_id]
        try:
            meta = await self._get(f"/texts/{text_id}")
        except FojinAPIError:
            return None
        cbeta_id = meta.get("cbeta_id") if isinstance(meta, dict) else None
        if isinstance(cbeta_id, str) and cbeta_id:
            if len(self._cbeta_cache) >= 100_000:  # paranoia bound, ~10K texts real
                self._cbeta_cache.clear()
            self._cbeta_cache[text_id] = cbeta_id
            return cbeta_id
        return None

    async def _enrich_parallel_urns(self, parallels: list[dict[str, Any]]) -> None:
        """Fill each parallel's ``urn`` in place from its reader_ref.text_id.

        Only fojin-native parallels (real text_id > 0) are resolvable; inline
        MITRA foreign sentences (text_id 0) have no fojin work to cite and keep
        urn=None. Distinct text_ids are fetched once, concurrently, capped."""
        want = [
            p for p in parallels
            if p.get("urn") is None
            and isinstance(p.get("reader_ref"), dict)
            and isinstance(p["reader_ref"].get("text_id"), int)
            and p["reader_ref"]["text_id"] > 0
        ]
        distinct_ids = list({p["reader_ref"]["text_id"] for p in want})[:_MAX_URN_ENRICH_LOOKUPS]
        if not distinct_ids:
            return
        cbeta_by_id = dict(
            zip(
                distinct_ids,
                await asyncio.gather(*(self._text_cbeta_id(tid) for tid in distinct_ids)),
                strict=True,
            )
        )
        for p in want:
            ref = p["reader_ref"]
            cbeta_id = cbeta_by_id.get(ref["text_id"])
            if cbeta_id:
                p["urn"] = build_urn(cbeta_id, ref.get("juan_num"))

    async def lookup_dictionary(self, term: str, limit: int = 10) -> dict[str, Any]:
        """Buddhist dictionary lookup across fojin's 32 dictionaries."""
        data = await self._get(
            "/dictionary/search", {"q": term, "size": _clamp(limit, 1, 50)}
        )
        return {"query": term, "entries": _as_list(data, "results", "entries")}

    async def lookup_entity(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Knowledge-graph entity search (persons, places, works, terms)."""
        # /kg/entities takes `limit` (not `size` like search/dictionary do);
        # FastAPI silently drops unknown params, so the wrong name means the
        # caller's limit never arrives.
        data = await self._get(
            "/kg/entities", {"q": query, "limit": _clamp(limit, 1, 50)}
        )
        return {"query": query, "entities": _as_list(data, "results", "entities")}

    async def resolve_urn(self, urn: str) -> dict[str, Any]:
        """Resolve a fojin URN → reader URL + existence (server-authoritative)."""
        # httpx percent-encodes '#' in query params; pre-encoding here would
        # double-encode it into a literal "%23" on the server side.
        return await self._get("/urn/resolve", {"urn": urn})

    async def verify_quote(
        self, quote: str, *, cite: str | None = None, juan: int | None = None
    ) -> dict[str, Any]:
        """Open-world verbatim quote verification against the whole corpus.

        The server's verdict shape is already agent-facing (verbatim/bucket/
        matches-with-URNs/closest/caveats), so it passes through unshaped."""
        params: dict[str, Any] = {"q": quote}
        if cite:
            params["cite"] = cite
        if juan is not None:
            params["juan"] = juan
        return await self._get("/verify/quote", params)


# ── pure reshaping (unit-tested with plain dicts) ────────────────────────


def shape_search_results(data: Any) -> dict[str, Any]:
    """Normalize /search/semantic into hits that each carry a URN.

    Robust to the two shapes the field has had: a top-level ``results`` list of
    ``SemanticSearchHit``. Each hit gets a juan-level ``urn`` built from its
    ``cbeta_id`` (None when the source has no round-trippable id)."""
    hits_in = _as_list(data, "results")
    hits_out: list[dict[str, Any]] = []
    for h in hits_in:
        if not isinstance(h, dict):
            continue
        hits_out.append(
            {
                "urn": build_urn(h.get("cbeta_id"), h.get("juan_num")),
                "text_id": h.get("text_id"),
                "juan_num": h.get("juan_num"),
                "title_zh": h.get("title_zh"),
                "cbeta_id": h.get("cbeta_id"),
                "snippet": h.get("snippet"),
                "score": h.get("similarity_score", h.get("score")),
            }
        )
    return {"total": _as_int(data, "total", len(hits_out)), "results": hits_out}


def shape_passage(data: Any) -> dict[str, Any]:
    """Normalize a JuanContentResponse, adding its URN."""
    d = data if isinstance(data, dict) else {}
    return {
        "urn": build_urn(d.get("cbeta_id"), d.get("juan_num")),
        "text_id": d.get("text_id"),
        "cbeta_id": d.get("cbeta_id"),
        "title_zh": d.get("title_zh"),
        "juan_num": d.get("juan_num"),
        "total_juans": d.get("total_juans"),
        "lang": d.get("lang", "lzh"),
        "content": d.get("content"),
        "char_count": d.get("char_count"),
    }


def shape_parallels(data: Any) -> dict[str, Any]:
    """Flatten a JuanAlignmentResponse into a list of parallel passages.

    The real envelope is ``entries[] -> {chunk_index, chunk_text, parallels[]}``
    where each parallel is a ``ParallelPair`` keyed by internal text_id (NOT
    cbeta_id). We flatten to one row per parallel, tagged with the source chunk
    it aligns to, and carry each parallel's ``reader_ref`` = {text_id, juan_num,
    chunk_index} — fojin's real deep-link handle. ``urn`` starts None here and is
    filled by the client's bounded text_id→cbeta_id enrichment pass (a
    ``ParallelPair`` carries no cbeta_id to build one from inline).

    ``source="mitra-parallel"`` rows are inline foreign (Skt/Tib) sentences from
    MITRA with text_id 0 — no fojin work to cite, so they stay urn=None but keep
    their ``original_preview``/``original_lang`` text."""
    d = data if isinstance(data, dict) else {}
    out: list[dict[str, Any]] = []
    for entry in _as_list(d, "entries"):
        if not isinstance(entry, dict):
            continue
        src_chunk = entry.get("chunk_index")
        for p in _as_list(entry, "parallels"):
            if not isinstance(p, dict):
                continue
            out.append(
                {
                    "urn": None,  # enriched by FojinClient._enrich_parallel_urns
                    "lang": p.get("lang"),
                    "title": p.get("title") or "",
                    "text": p.get("chunk_text"),
                    "confidence": p.get("confidence"),
                    "source": p.get("source", "fojin"),
                    "original_preview": p.get("original_preview"),
                    "original_lang": p.get("original_lang"),
                    "aligns_source_chunk": src_chunk,
                    "reader_ref": {
                        "text_id": p.get("text_id"),
                        "juan_num": p.get("juan_num"),
                        "chunk_index": p.get("chunk_index"),
                    },
                }
            )
    return {
        "source": {
            "text_id": d.get("text_id"),
            "juan_num": d.get("juan_num"),
            "total_chunks": d.get("total_chunks"),
            "chunks_with_parallels": d.get("chunks_with_parallels"),
        },
        "parallels": out,
    }


# ── small helpers ────────────────────────────────────────────────────────


def _clamp(n: int, lo: int, hi: int) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, n))


def _as_list(data: Any, *keys: str) -> list[Any]:
    """Return the first key in ``data`` whose value is a list; [] if none.

    Tolerates both ``{"results": [...]}`` envelopes and a bare top-level list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


def _as_int(data: Any, key: str, default: int) -> int:
    if isinstance(data, dict):
        val = data.get(key)
        if isinstance(val, int):
            return val
    return default
