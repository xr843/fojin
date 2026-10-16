"""Pasted-passage locator: when the user pastes canon text, put that passage in context.

19% of /chat questions contain a verbatim canon passage (users read elsewhere and
come to fojin to have it explained), yet only half of those answers had the pasted
passage in their retrieved context (production replay 2026-10-05) — vector recall
returns thematically similar chunks, often commentaries, not the passage itself.
The miss concentrates in 俱舍 / 婆沙 and their 疏, which is what core users read.

Design (same contract as ``quote_lookup``: **ES shortlists, Postgres decides**):

1. Split the message into clauses at punctuation. Users wrap the passage in modern
   prose (「请解释：……是什么意思」), so we never require the whole message to match.
2. ES shortlists candidate fascicles that contain any of the longer clauses.
3. For each candidate's real retrieval chunks (``text_embeddings``) find the
   longest run of *consecutive* user clauses that appears verbatim (normalised:
   NFKC + 繁→简 + punctuation stripped). A chunk qualifies only with
   ≥ ``MIN_WINDOW_HAN`` 汉字 of the user's own text inside it.
4. Several texts can carry the same passage (commentaries quote the sutra). Among
   the longest windows prefer root canon over 卍續藏, then the lowest number —
   the sutra before the treatise before the commentary. That ordering only helps
   if the root text is *among the candidates*: a passage commentaries quote over
   and over fills the BM25 shortlist with them (《起信論》「心真如者……」: 8 of 8
   slots went to its 疏 and 《釋摩訶衍論》, the 論 itself never got fetched). So a
   second, smaller shortlist is drawn from 大正藏 經律論 proper (T0001–T1692)
   and merged in. Relevance ranking still favours short fascicles, so once the
   best window is known we also ask ES directly which 經律論 carry it verbatim,
   lowest number first, and let those compete for the window too
   (``_root_carriers``). A window found in more
   than ``AMBIGUOUS_TEXTS`` texts is a stock formula (如是我聞……) and is not
   injected: it locates nothing in particular. When the pick is root canon the
   count that matters is how many *root* texts carry it: 疏 quoting a sutra line
   do not make the sutra ambiguous (《心經》「心無罣礙……」 is in ~50 texts but only
   the 3–4 心經 translations among 經律論), while 如是我聞一時佛在舍衛國 is in 71
   經律論 and stays suppressed.

The located chunk is returned in the same shape as ``similarity_search`` rows so
it travels through the existing pipeline (drawer coordinates, citation guard)
unchanged. Thresholds and their evidence: ``eval/paste_locate/GATE.md``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.quote_verifier import _STRIP_PUNCT_RE, _t2s, fold_variants

logger = logging.getLogger(__name__)

# A located window must contain at least this many 汉字 of the user's own text.
# Same floor as the measurement that sized the gap; below it short stock phrases
# (世尊言、如是我聞) would "locate" half the canon.
MIN_WINDOW_HAN = 12
# Clauses sent to ES as shortlist probes must carry at least this many 汉字;
# 2–3 character clauses match everywhere and only add noise to the shortlist.
MIN_PROBE_HAN = 4
# Bounded work per message.
MAX_CLAUSES = 24
SHORTLIST_JUANS = 8
# Extra juans drawn only from 大正藏 經律論 proper — the root texts that 疏/鈔/記
# quote — so commentaries cannot crowd the root out of the candidate set.
ROOT_SHORTLIST_JUANS = 4
# 大正藏 T0001–T1692 是經、律、論本身；T1693 起是經疏、律疏、論疏、諸宗、史傳、事彙、
# 外教、目錄。cbeta_id 是零填充的 keyword，字典序区间即编号区间（含 T0220a 这类带后缀的）。
ROOT_CANON_FILTER = {"range": {"cbeta_id": {"gte": "T0001", "lt": "T1693"}}}
# After the window is found: this many 經律論 that carry it verbatim, lowest
# number first, join the candidates (see ``_root_carriers``).
ROOT_CARRIER_TEXTS = 4
# A window carried by more texts than this is a stock formula, not a location.
AMBIGUOUS_TEXTS = 20

_SPLIT_RE = re.compile(r"[\s\W_]+")
_HAN_RE = re.compile(r"[㐀-鿿豈-﫿\U00020000-\U0002ffff]")
_CANON_ID_RE = re.compile(r"^([A-Z]+)(\d+)")


def han_count(s: str) -> int:
    return len(_HAN_RE.findall(s))


# 逐字繁→简映射缓存。整段跑 OpenCC 约 3 ms/千字，而一次定位要比对 10–18 万字
# 候选正文（生产实测 270–570 ms，超过延迟门）。按字转换后进缓存，之后只是 str.translate。
# 用户文本与候选正文走同一个函数，两边口径一致；代价是丢掉 OpenCC 极少数的词组级
# 转换——那只会让个别匹配落空，不会造成错配。
_CHAR_MAP: dict[int, str] = {}


def _norm_char(ch: str) -> str:
    """One raw character → its normalised form ('' for punctuation/whitespace)."""
    cp = ord(ch)
    hit = _CHAR_MAP.get(cp)
    if hit is None:
        folded = unicodedata.normalize("NFKC", ch)
        folded = fold_variants(_t2s.convert(folded)) if folded else folded
        hit = _STRIP_PUNCT_RE.sub("", folded).lower()
        _CHAR_MAP[cp] = hit
    return hit


def fast_normalise(s: str) -> str:
    """Per-character equivalent of ``quote_verifier.normalise_for_match``."""
    missing = {c for c in set(s) if ord(c) not in _CHAR_MAP}
    for c in missing:
        _norm_char(c)
    return s.translate(_CHAR_MAP)


def span_indices(raw: str, normalised_needle: str) -> tuple[int, int] | None:
    """[start, end) in ``raw`` of the stretch whose normalised form is the needle."""
    if not normalised_needle:
        return None
    pieces: list[str] = []
    owner: list[int] = []
    for i, ch in enumerate(raw):
        n = _norm_char(ch)
        pieces.append(n)
        owner.extend([i] * len(n))
    k = "".join(pieces).find(normalised_needle)
    if k < 0:
        return None
    return owner[k], owner[k + len(normalised_needle) - 1] + 1


def raw_span(raw: str, normalised_needle: str) -> str | None:
    """The stretch of ``raw`` (original punctuation kept) whose normalised form is
    ``normalised_needle``. Used to re-query ES with the *source's* own clause
    boundaries — the user's punctuation rarely matches the source's, and a phrase
    query split at the user's commas silently matches nothing."""
    idx = span_indices(raw, normalised_needle)
    return None if idx is None else raw[idx[0] : idx[1]]


_TITLE_RE = re.compile(r"《([^》]{1,60})》|〈([^〉]{1,60})〉")


def named_titles(message: str) -> list[str]:
    return [a or b for a, b in _TITLE_RE.findall(message)]


def split_clauses(message: str) -> list[str]:
    """Raw clauses of ``message`` that carry at least two 汉字, in order.
    Text inside 《》/〈〉 is a book title, not a pasted passage — a long sutra
    title alone matched its own entry in 眾經目錄 and got injected."""
    body = _TITLE_RE.sub("，", message)
    out = [c for c in _SPLIT_RE.split(body) if han_count(c) >= 2]
    return out[:MAX_CLAUSES]


@dataclass(frozen=True)
class Window:
    start: int  # clause index, inclusive
    end: int  # clause index, exclusive
    han: int

    def text(self, clauses: list[str]) -> str:
        return "，".join(clauses[self.start : self.end])


def best_window(norm_clauses: list[str], haystack: str) -> Window | None:
    """Longest run of consecutive clauses whose concatenation is verbatim in
    ``haystack`` (both already normalised). Consecutive and
    contiguous on purpose: a pasted passage is one continuous stretch of the
    source, so clauses must abut there too — unlike an elided quote.
    Inputs are ``fast_normalise``-d."""
    best: Window | None = None
    n = len(norm_clauses)
    for i in range(n):
        if norm_clauses[i] not in haystack:
            continue
        j = i + 1
        joined = norm_clauses[i]
        while j < n and (joined + norm_clauses[j]) in haystack:
            joined += norm_clauses[j]
            j += 1
        w = Window(i, j, han_count(joined))
        if best is None or w.han > best.han:
            best = w
    return best


def canon_rank_key(cbeta_id: str | None) -> tuple[int, int, str]:
    """Root canon first, 卍續藏 (almost all commentary) last, then the lowest
    number — within 大正藏 that orders 經 before 論 before 疏/史傳."""
    cid = cbeta_id or ""
    m = _CANON_ID_RE.match(cid)
    if not m:
        return (3, 10**6, cid)
    prefix, num = m.group(1), int(m.group(2))
    tier = 0 if prefix == "T" else 2 if prefix == "X" else 1
    return (tier, num, cid)


@dataclass(frozen=True)
class Located:
    chunk: dict  # same keys as embedding.similarity_search rows
    window_text: str
    window_han: int
    texts_with_window: int
    # The window as it reads in the source chunk (source punctuation, hard wraps
    # kept); None when it could not be mapped back. Shown to the reader.
    source_span: str | None = None


def pick_located(
    clauses: list[str],
    chunks: list[dict],
    *,
    named_text_ids: frozenset[int] = frozenset(),
    min_han: int = MIN_WINDOW_HAN,
) -> tuple[dict, Window] | None:
    """Best (chunk, window) among candidate chunks, or None.

    Longest window first; on a tie the text the user named in 《》, then
    ``canon_rank_key``, then reading order.

    Quotation marks are deliberately *not* a filter: CBETA puts the Buddha's own
    words in 「」, so "only quoted ⇒ not a source" suppressed sutra dialogue
    wholesale (eval/paste_locate/GATE.md 修订 4). The risk that rule targeted —
    a secular line quoted inside a Buddhist text being passed off as its source —
    is handled by labelling the injected block instead (rag_retrieval)."""
    norm = [fast_normalise(c) for c in clauses]
    scored: list[tuple[int, int, tuple, int, int, dict, Window]] = []
    for ch in chunks:
        raw = ch.get("chunk_text") or ""
        w = best_window(norm, fast_normalise(raw))
        if w is None or w.han < min_han:
            continue
        named_rank = 0 if ch.get("text_id") in named_text_ids else 1
        scored.append((-w.han, named_rank, canon_rank_key(ch.get("cbeta_id")), ch["juan_num"], ch["chunk_index"], ch, w))
    if not scored:
        return None
    scored.sort(key=lambda s: s[:5])
    return scored[0][5], scored[0][6]


async def _shortlist(
    es: AsyncElasticsearch,
    clauses: list[str],
    *,
    text_ids: list[int] | None = None,
    root_only: bool = False,
    size: int = SHORTLIST_JUANS,
) -> list[tuple[int, int]]:
    probes = [c for c in clauses if han_count(c) >= MIN_PROBE_HAN]
    if not probes:
        return []
    filters: list[dict] = [{"term": {"lang": "lzh"}}]
    if text_ids:
        filters.append({"terms": {"text_id": text_ids}})
    if root_only:
        filters.append(ROOT_CANON_FILTER)
    # 不用 match_phrase：CBETA 原文每 17–20 字一个硬换行，cjk_bigram 不跨换行生成二元组，
    # 所以跨行的句子做短语查询必然落空（随机抽 80 句真经文，短语粗筛只找回 71%）。
    # 改为逐句的二元组词袋、命中 75% 即入围：一处换行只丢一个二元组。是否真在原文里，
    # 仍由 Postgres 逐字确认（去掉空白后比对），粗筛放宽不影响精度。
    body = {
        "query": {
            "bool": {
                "should": [
                    {"match": {"content": {"query": c, "analyzer": "cjk_content", "minimum_should_match": "75%"}}}
                    for c in probes
                ],
                "minimum_should_match": 1,
                "filter": filters,
            }
        },
        "size": size,
        "_source": ["text_id", "juan_num"],
    }
    resp = await es.search(index="text_contents", body=body, timeout="5s")
    out: list[tuple[int, int]] = []
    for h in resp["hits"]["hits"]:
        src = h.get("_source") or {}
        if isinstance(src.get("text_id"), int) and isinstance(src.get("juan_num"), int):
            out.append((src["text_id"], src["juan_num"]))
    return out


def is_root_canon(cbeta_id: str | None) -> bool:
    """大正藏 經律論 proper — the same range as ``ROOT_CANON_FILTER``."""
    cid = cbeta_id or ""
    return "T0001" <= cid < "T1693"


async def _count_texts_with(es: AsyncElasticsearch, source_span: str) -> int:
    """How many distinct texts carry the passage. Split at the *source's*
    punctuation (see ``raw_span``) so every clause is a phrase that really exists."""
    # 按原文自己的换行再切一刀：跨换行的短语查不到（见 _shortlist），行内的片段都能精确命中。
    window_clauses = [c for c in _SPLIT_RE.split(source_span) if han_count(c) >= 2]
    if not window_clauses:
        return 0
    body = {
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"content": {"query": c, "analyzer": "cjk_content"}}} for c in window_clauses
                ],
                "filter": [{"term": {"lang": "lzh"}}],
            }
        },
        "size": 0,
        "aggs": {"texts": {"cardinality": {"field": "text_id"}}},
    }
    resp = await es.search(index="text_contents", body=body, timeout="5s")
    return int(resp["aggregations"]["texts"]["value"])


async def _root_carriers(es: AsyncElasticsearch, source_span: str) -> tuple[int, list[tuple[int, int]]]:
    """(how many 經律論 carry the window verbatim, the first ``ROOT_CARRIER_TEXTS``
    of them by 經號 — one fascicle each).

    The shortlists rank by relevance, which favours short fascicles: 《金剛經》 is
    one long juan and lost every slot to 釋經論 quoting it, even with the 經律論-only
    shortlist doubled. What we actually want is "the lowest-numbered root text
    that has this passage", so ask exactly that. ``content.nopunct`` drops
    punctuation and CBETA hard wraps between Han characters, so one phrase query
    over the whole window works whatever the source's line breaks — but not every
    mark: a full-width 「．」 (common in 卍續藏) still breaks the bigram chain and the
    phrase silently matches nothing. So the query is stripped to bare characters."""
    bare = _SPLIT_RE.sub("", source_span)
    body = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"lang": "lzh"}},
                    ROOT_CANON_FILTER,
                    {"match_phrase": {"content.nopunct": {"query": bare}}},
                ]
            }
        },
        "sort": [{"cbeta_id": "asc"}, {"juan_num": "asc"}],
        "collapse": {"field": "text_id"},
        "size": ROOT_CARRIER_TEXTS,
        "_source": ["text_id", "juan_num"],
        "aggs": {"texts": {"cardinality": {"field": "text_id"}}},
    }
    resp = await es.search(index="text_contents", body=body, timeout="5s")
    juans: list[tuple[int, int]] = []
    for h in resp["hits"]["hits"]:
        src = h.get("_source") or {}
        if isinstance(src.get("text_id"), int) and isinstance(src.get("juan_num"), int):
            juans.append((src["text_id"], src["juan_num"]))
    return int(resp["aggregations"]["texts"]["value"]), juans


# 归一化书名 → text_id 列表。全库约一万部，进程内缓存一次，书名的繁简写法就都能对上。
_TITLE_INDEX: dict[str, list[int]] | None = None


async def _resolve_named(db: AsyncSession, titles: list[str]) -> list[int]:
    """lzh texts whose title equals a title the user wrote in 《》 (繁简 folded)."""
    global _TITLE_INDEX
    wanted = {fast_normalise(t) for t in titles if han_count(t) >= 2}
    if not wanted:
        return []
    if _TITLE_INDEX is None:
        rows = (await db.execute(sql_text("SELECT id, title_zh FROM buddhist_texts WHERE lang = 'lzh'"))).all()
        index: dict[str, list[int]] = {}
        for tid, title in rows:
            if title:
                index.setdefault(fast_normalise(title), []).append(tid)
        _TITLE_INDEX = index
    out: list[int] = []
    for w in wanted:
        out.extend(_TITLE_INDEX.get(w, []))
    return out[:20]


async def _fetch_chunks(db: AsyncSession, juans: list[tuple[int, int]]) -> list[dict]:
    if not juans:
        return []
    pairs = ",".join(f"({int(t)},{int(j)})" for t, j in juans)
    rows = (
        await db.execute(
            sql_text(
                "SELECT te.text_id, te.juan_num, te.chunk_index, te.chunk_text, "
                "COALESCE(bt.title_zh, '') AS title_zh, bt.lang, bt.source_id, bt.cbeta_id "
                "FROM text_embeddings te JOIN buddhist_texts bt ON bt.id = te.text_id "
                f"WHERE (te.text_id, te.juan_num) IN ({pairs}) AND bt.lang = 'lzh'"  # nosec B608 — ints only
            )
        )
    ).all()
    return [
        {
            "text_id": r[0],
            "juan_num": r[1],
            "chunk_index": r[2],
            "chunk_text": r[3],
            # An exact verbatim location: shown to the reader as full similarity.
            "score": 1.0,
            "title_zh": r[4],
            "lang": r[5] or "lzh",
            "source_id": r[6],
            "cbeta_id": r[7],
        }
        for r in rows
    ]


async def locate_pasted_passage(es: AsyncElasticsearch, db: AsyncSession, message: str) -> Located | None:
    """The retrieval chunk holding the canon passage the user pasted, or None."""
    clauses = split_clauses(message)
    if han_count("".join(clauses)) < MIN_WINDOW_HAN:
        return None
    named_ids = await _resolve_named(db, named_titles(message))
    general, root = await asyncio.gather(
        _shortlist(es, clauses),
        _shortlist(es, clauses, root_only=True, size=ROOT_SHORTLIST_JUANS),
    )
    juans = general + [j for j in root if j not in general]
    if named_ids:
        # 用户点名的书即使不在通用候选的前几名里，也要拿来比一比
        juans += [j for j in await _shortlist(es, clauses, text_ids=named_ids) if j not in juans]
    chunks = await _fetch_chunks(db, juans)
    picked = pick_located(clauses, chunks, named_text_ids=frozenset(named_ids))
    if picked is None:
        return None
    chunk, window = picked
    span = _source_span(chunk, clauses, window)
    if not span:
        return Located(chunk=chunk, window_text=window.text(clauses), window_han=window.han, texts_with_window=0)
    n_texts, (n_root, carriers) = await asyncio.gather(_count_texts_with(es, span), _root_carriers_safe(es, span))
    extra = [j for j in carriers if j not in juans]
    if extra:
        # 含这段的经律论（经号最小的几部）补进候选，同长窗口按 canon_rank_key 本经胜出
        chunks += await _fetch_chunks(db, extra)
        repicked = pick_located(clauses, chunks, named_text_ids=frozenset(named_ids))
        if repicked is not None and repicked[0] is not chunk:
            chunk, new_window = repicked
            if new_window != window:  # 窗口变了（更长），两个计数都按新窗口重数
                window = new_window
                span = _source_span(chunk, clauses, window)
                if span:
                    n_texts, (n_root, _) = await asyncio.gather(
                        _count_texts_with(es, span), _root_carriers_safe(es, span)
                    )
                else:
                    n_texts, n_root = 0, 0
            else:
                span = _source_span(chunk, clauses, window) or span
    if n_texts > AMBIGUOUS_TEXTS:
        # 本经本论被注疏大量引用不算「套语」：选中经律论时只数经律论里有几部含这段
        if n_root is None or not is_root_canon(chunk.get("cbeta_id")):
            n_root = n_texts
        if n_root > AMBIGUOUS_TEXTS:
            logger.info(
                "paste_locate ambiguous: window in %d texts / %d root texts (>%d), not injecting (%r)",
                n_texts, n_root, AMBIGUOUS_TEXTS, window.text(clauses)[:30],
            )
            return None
    return Located(
        chunk=chunk,
        window_text=window.text(clauses),
        window_han=window.han,
        texts_with_window=n_texts,
        source_span=span,
    )


def _source_span(chunk: dict, clauses: list[str], window: Window) -> str | None:
    window_norm = "".join(fast_normalise(c) for c in clauses[window.start : window.end])
    return raw_span(chunk.get("chunk_text") or "", window_norm)


async def _root_carriers_safe(es: AsyncElasticsearch, span: str) -> tuple[int | None, list[tuple[int, int]]]:
    """``_root_carriers`` or (None, []) — it only ever improves the pick, so a
    failure falls back to the shortlist result and the whole-canon formula count."""
    try:
        return await _root_carriers(es, span)
    except Exception:
        logger.warning("paste_locate root-carrier lookup failed; keeping shortlist pick", exc_info=True)
        return None, []


def inject_located(located_chunk: dict, results: list[dict], max_chunks: int) -> list[dict]:
    """Located chunk takes slot #1 — the user literally pasted it — replacing any
    other chunk of the same fascicle (results are already one-per-fascicle)."""
    key = (located_chunk["text_id"], located_chunk["juan_num"])
    others = [r for r in results if (r["text_id"], r["juan_num"]) != key]
    return [located_chunk, *others][:max_chunks]
