"""RAG retrieval: pgvector semantic similarity search + reranking."""

import asyncio
import logging
import re
import time

import httpx
from opencc import OpenCC
from sqlalchemy import or_, select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import async_session
from app.models.dictionary import DictionaryEntry
from app.schemas.chat import ChatSource
from app.services.embedding import generate_embedding, similarity_search, source_similarity_search
from app.services.precise_retrieval import try_precise_text_retrieval

logger = logging.getLogger(__name__)

# Minimum first-stage (vector cosine) score for a chunk to survive into the
# rerank candidate pool. Kept deliberately low because the cross-encoder reranker
# — not this coarse cosine floor — is the real relevance filter: a base sutra can
# lose the cosine race to its own dense commentaries yet score highest under the
# reranker, so an aggressive pre-filter here would discard it before the reranker
# ever sees it. The final top-MAX_CONTEXT_CHUNKS is chosen on the blended
# (vector + cross-encoder) score, which keeps genuine noise out of the answer.
MIN_RELEVANCE_SCORE = 0.25

# Maximum chunks to send to LLM after reranking (fewer but more relevant = better answers)
MAX_CONTEXT_CHUNKS = 5

# Upper bound on candidates cross-encoded per query (latency/cost + request-size
# guardrail). The post-dedup pool is well under this today; it just caps growth.
RERANK_CANDIDATE_LIMIT = 32

# Trilingual RAG: enable per-language retrieval + alignment-aware merging.
# When True, retrieve_rag_context fetches separately from lzh/pi/bo and then
# attaches parallel_chunks to primary hits via alignment_pairs lookup.
# Controlled by env var so it can be disabled in one place if needed.
ENABLE_PARALLEL_RAG = settings.enable_parallel_rag if hasattr(settings, "enable_parallel_rag") else True

# Per-lang top-k budgets for parallel mode. Total retrieved = LZH_K + PI_K + BO_K.
# Keep larger for lzh since 95%+ users read Chinese and primary narrative stays in lzh.
# LZH_K is deliberately generous (well above MAX_CONTEXT_CHUNKS): the cross-encoder
# reranker only re-scores what vector search already retrieved, so a base sutra
# that loses the first-stage cosine race to its own dense commentaries (the 心经
# 本经 vs 心經注疏 failure mode) must still be inside this candidate pool for the
# reranker to be able to promote it. Final context is still capped at
# MAX_CONTEXT_CHUNKS after reranking.
PARALLEL_LZH_K = 15
PARALLEL_PI_K = 4
PARALLEL_BO_K = 4

# --- 本经召回保底 (root-sutra reserved slot) ---------------------------------
# When a user names a root sutra, dense commentaries out-rank the terse root in
# BOTH vector recall and the cross-encoder rerank, so the named sutra never
# reaches the LLM (the 本经召回缺口: e.g. "心经核心思想" → top-5 is 100% 心經注疏,
# root 般若波羅蜜多心經 absent even when force-fed into the candidate pool).
# Fix: detect the named root via a curated alias map and reserve it one context
# slot, bypassing both the cosine race and the rerank burial. Keyed by canonical
# root cbeta_id (stable); resolved to text_id at runtime. Maps the highest-traffic
# sutras only — high precision, no reliance on the dirty `category` field.
_ROOT_SUTRA_ALIASES: dict[str, str] = {
    "般若波羅蜜多心經": "T0251", "般若波罗蜜多心经": "T0251", "心經": "T0251", "心经": "T0251",
    "金剛般若": "T0235", "金刚般若": "T0235", "金剛經": "T0235", "金刚经": "T0235",
    "妙法蓮華經": "T0262", "妙法莲华经": "T0262", "法華經": "T0262", "法华经": "T0262",
    "普門品": "T0262", "普门品": "T0262",
    "觀無量壽經": "T0365", "观无量寿经": "T0365", "觀無量壽佛經": "T0365", "观无量寿佛经": "T0365",
    "無量壽經": "T0360", "无量寿经": "T0360",
    "阿彌陀經": "T0366", "阿弥陀经": "T0366",
    "地藏菩薩本願": "T0412", "地藏菩萨本愿": "T0412", "地藏經": "T0412", "地藏经": "T0412",
    "藥師經": "T0450", "药师经": "T0450", "藥師琉璃光": "T0450", "药师琉璃光": "T0450",
    "維摩詰": "T0475", "维摩诘": "T0475", "維摩經": "T0475", "维摩经": "T0475",
    "楞伽": "T0670",
    "圓覺經": "T0842", "圆觉经": "T0842",
    "首楞嚴": "T0945", "首楞严": "T0945", "楞嚴經": "T0945", "楞严经": "T0945",
    "大悲咒": "T1060", "千手千眼": "T1060",
    "六祖壇經": "T2008", "六祖坛经": "T2008", "壇經": "T2008", "坛经": "T2008",
    "四十二章經": "T0784", "四十二章经": "T0784",
    # 普门品 (Avalokiteśvara chapter) is fascicle of the Lotus T0262, not a
    # standalone cbeta_id — the per-chunk similarity picks the right fascicle.
}
# Longest alias first so e.g. "观无量寿经" (T0365) wins over "无量寿经" (T0360).
_ROOT_ALIAS_KEYS_BY_LEN = sorted(_ROOT_SUTRA_ALIASES, key=len, reverse=True)
_root_text_id_cache: dict[str, int | None] = {}

# The 2-char aliases 心经/坛经 are substrings of common non-sutra phrases that
# split 经 into a following compound: 担心|经济, 关心|经验, 论坛|经历, 开心|经常…
# Reject such a match when the char right after the alias starts a 经-word.
_AMBIGUOUS_SHORT_ALIASES = {"心经", "心經", "坛经", "壇經"}
_JING_COMPOUND_TAIL = set("济濟验驗常过過营營历歷理典商销銷书書文手度络絡费費办辦纬緯由")

# --- 义理术语→本典 (doctrine-term root slot, Case 2 of 本经召回缺口) ----------
# Abstract doctrine questions name no sutra ("缘起性空怎么理解"), so
# _detect_named_root never fires, and the foundational treatise (中论,
# 成唯识论…) loses the cosine race to dense later commentaries that repeat
# the term more often (BM25 would skew the same way — commentaries have
# higher term density than the source text, which is why hybrid keyword
# retrieval is NOT the fix here). Same curated-map + reserved-slot approach
# as the named-sutra fix above, keyed on high-precision doctrine terms.
# Multi-char terms only; root availability prod-verified 2026-06-11 (all
# mapped texts have content + embeddings). Known accepted false positives
# (deliberate trade-off, cost confined to the last slot on a Buddhist
# site): lexicalized chengyu 不二法门/本来面目/直指人心 and secular 顿悟
# also fire in everyday usage. Cross-boundary traps (毕竟空闲, 真空性质)
# are guarded via _AMBIGUOUS_DOCTRINE_TAILS below.
_DOCTRINE_TERM_ROOTS: dict[str, str] = {
    # 中观 → 中论 T1564
    "缘起性空": "T1564", "緣起性空": "T1564", "性空缘起": "T1564", "性空緣起": "T1564",
    "八不中道": "T1564", "空性": "T1564", "自性空": "T1564", "毕竟空": "T1564", "畢竟空": "T1564",
    # 唯识 → 成唯识论 T1585
    "唯识": "T1585", "唯識": "T1585", "阿赖耶": "T1585", "阿賴耶": "T1585",
    "末那识": "T1585", "末那識": "T1585", "三自性": "T1585",
    "遍计所执": "T1585", "遍計所執": "T1585", "依他起": "T1585", "圆成实": "T1585", "圓成實": "T1585",
    "转识成智": "T1585", "轉識成智": "T1585", "八识": "T1585", "八識": "T1585",
    # 佛性/如来藏 → 大般涅槃经 T0374
    "佛性": "T0374", "如来藏": "T0374", "如來藏": "T0374",
    "一阐提": "T0374", "一闡提": "T0374", "常乐我净": "T0374", "常樂我淨": "T0374",
    # 天台 → 摩诃止观 T1911
    "一念三千": "T1911", "三谛圆融": "T1911", "三諦圓融": "T1911",
    "一心三观": "T1911", "一心三觀": "T1911",
    # 华严宗义 → 华严五教章 T1866 (法藏)：四法界/十玄/六相 are patriarch-treatise
    # vocabulary — the 80-juan sutra never states them as doctrines, so a scoped
    # search over T0279 returns weakly related chunks. T1866 expounds them
    # directly (202 chunks, prod-verified). 因陀罗网 stays on the sutra: the
    # 帝网 imagery genuinely lives there.
    "法界缘起": "T1866", "法界緣起": "T1866", "四法界": "T1866",
    "事事无碍": "T1866", "事事無礙": "T1866", "十玄门": "T1866", "十玄門": "T1866",
    "六相圆融": "T1866", "六相圓融": "T1866",
    "因陀罗网": "T0279", "因陀羅網": "T0279",
    # 净土 → 阿弥陀经 T0366；带业往生的经证是观经下品下生 → T0365
    "念佛法门": "T0366", "念佛法門": "T0366", "净土法门": "T0366", "淨土法門": "T0366",
    "带业往生": "T0365", "帶業往生": "T0365", "西方极乐": "T0366", "西方極樂": "T0366",
    # 禅宗 → 六祖坛经 T2008
    "明心见性": "T2008", "明心見性": "T2008", "顿悟": "T2008", "頓悟": "T2008",
    "本来面目": "T2008", "本來面目": "T2008", "直指人心": "T2008", "见性成佛": "T2008", "見性成佛": "T2008",
    # 不二 → 维摩诘经 T0475
    "不二法门": "T0475", "不二法門": "T0475",
    # 法华 → 法华经 T0262
    "一佛乘": "T0262", "会三归一": "T0262", "會三歸一": "T0262", "开权显实": "T0262", "開權顯實": "T0262",
    # 根本教义 → 杂阿含 T0099
    "四圣谛": "T0099", "四聖諦": "T0099", "八正道": "T0099",
    "十二因缘": "T0099", "十二因緣": "T0099", "四念处": "T0099", "四念處": "T0099",
    "三法印": "T0099",
}
_DOCTRINE_KEYS_BY_LEN = sorted(_DOCTRINE_TERM_ROOTS, key=len, reverse=True)

# Cross-boundary guard, same mechanism as _AMBIGUOUS_SHORT_ALIASES: these terms'
# last char also heads common secular compounds, so 毕竟空|闲时间 ("after all,
# little free time") or 真空|性质 ("properties of vacuum", matching 空+性 across
# the word boundary) must not fire. Reject an occurrence when the next char
# completes such a compound; accept if ANY occurrence has a clean tail.
_AMBIGUOUS_DOCTRINE_TAILS: dict[str, set[str]] = {
    "毕竟空": set("气氣调調间間白闲閒着隙位缺旷曠地"),
    "畢竟空": set("气氣调調间間白闲閒着隙位缺旷曠地"),
    "空性": set("质質能格"),
}

# --- 规范名句→本经 (canonical-phrase root slot, Case 3 of 本经召回缺口) --------
# Attribution questions quote a famous line without naming the sutra
# ("「色不异空」出自哪部经?"), so neither _detect_named_root nor
# _detect_doctrine_root fires, and the terse root loses the cosine race to its
# verbose 注疏 (prod-measured 2026-06-22: root recall@5 ≈ 0 on these). Same
# curated-map + reserved-slot fix as Cases 1-2. Keys are deliberately limited to
# sutra-DISTINCTIVE lines (a unique fingerprint of one root, both 简/繁 listed) so
# no ambiguity guard is needed. Non-distinctive法数 like 五蕴皆空 / 一切有为法 are
# excluded on purpose: they recur across canons + 注疏 and read as doctrine, not
# attribution, so they would mis-fire on 义理 questions and wrongly grab slot #1.
# Attribution → the user wants THE source, so a match joins the named tier (slot #1).
_CANONICAL_PHRASE_ROOTS: dict[str, str] = {
    # 般若波罗蜜多心经 T0251
    "色不异空": "T0251", "色不異空": "T0251", "空不异色": "T0251", "空不異色": "T0251",
    "色即是空": "T0251", "空即是色": "T0251",
    "照见五蕴皆空": "T0251", "照見五蘊皆空": "T0251", "度一切苦厄": "T0251",
    "不垢不净": "T0251", "不垢不淨": "T0251", "不增不减": "T0251", "不增不減": "T0251",
    "是诸法空相": "T0251", "是諸法空相": "T0251",
    "心无罣碍": "T0251", "心無罣礙": "T0251", "心无挂碍": "T0251", "心無掛礙": "T0251",
    "远离颠倒梦想": "T0251", "遠離顛倒夢想": "T0251",
    "揭谛揭谛": "T0251", "揭諦揭諦": "T0251",
    # 金刚般若波罗蜜经 T0235
    "应无所住而生其心": "T0235", "應無所住而生其心": "T0235",
    "如梦幻泡影": "T0235", "如夢幻泡影": "T0235", "如露亦如电": "T0235", "如露亦如電": "T0235",
    "若以色见我": "T0235", "若以色見我": "T0235", "以音声求我": "T0235", "以音聲求我": "T0235",
    "是人行邪道": "T0235", "凡所有相皆是虚妄": "T0235", "凡所有相皆是虛妄": "T0235",
    "过去心不可得": "T0235", "過去心不可得": "T0235", "应作如是观": "T0235", "應作如是觀": "T0235",
    # 六祖大师法宝坛经 T2008
    "菩提本无树": "T2008", "菩提本無樹": "T2008", "明镜亦非台": "T2008", "明鏡亦非臺": "T2008",
    "本来无一物": "T2008", "本來無一物": "T2008", "何处惹尘埃": "T2008", "何處惹塵埃": "T2008",
}
_PHRASE_KEYS_BY_LEN = sorted(_CANONICAL_PHRASE_ROOTS, key=len, reverse=True)


def _detect_doctrine_root(query: str) -> str | None:
    """Return the root cbeta_id for the longest curated doctrine term present in
    the query, or None. Longest-match mirrors _detect_named_root; no key currently
    nests inside another, so the sort is future-proofing for added terms (e.g. a
    bare "缘起" entry must never shadow "法界缘起")."""
    for term in _DOCTRINE_KEYS_BY_LEN:
        if term not in query:
            continue
        bad_tails = _AMBIGUOUS_DOCTRINE_TAILS.get(term)
        if bad_tails:
            start, real = 0, False
            while (pos := query.find(term, start)) != -1:
                tail = query[pos + len(term): pos + len(term) + 1]
                if not tail or tail not in bad_tails:
                    real = True
                    break
                start = pos + 1
            if not real:
                continue
        return _DOCTRINE_TERM_ROOTS[term]
    return None


def _detect_named_root(query: str) -> str | None:
    """Return the canonical root cbeta_id of the longest curated sutra alias that
    appears in the query, or None. Longest-match disambiguates nested names; the
    2-char ambiguous aliases are rejected when followed by a 经-compound char so
    e.g. "担心经济压力" does not mis-fire as 心經."""
    for alias in _ROOT_ALIAS_KEYS_BY_LEN:
        if alias not in query:
            continue
        if alias in _AMBIGUOUS_SHORT_ALIASES:
            # Accept only if SOME occurrence isn't followed by a 经-compound char.
            start, real = 0, False
            while (pos := query.find(alias, start)) != -1:
                tail = query[pos + len(alias): pos + len(alias) + 1]
                if not tail or tail not in _JING_COMPOUND_TAIL:
                    real = True
                    break
                start = pos + 1
            if not real:
                continue
        return _ROOT_SUTRA_ALIASES[alias]
    return None


def _detect_phrase_root(query: str) -> str | None:
    """Return the root cbeta_id for a curated canonical phrase quoted in the query,
    or None. Targets attribution questions ("「色不异空」出自哪部经?") where the user
    quotes a distinctive sutra line without naming the sutra. Phrases are ≥4 chars
    and sutra-specific, so a plain longest-first substring match suffices."""
    for phrase in _PHRASE_KEYS_BY_LEN:
        if phrase in query:
            return _CANONICAL_PHRASE_ROOTS[phrase]
    return None


async def _resolve_root_text_id(db: AsyncSession, cbeta_id: str) -> int | None:
    """Resolve a root cbeta_id → buddhist_texts.id (lzh), cached per process."""
    if cbeta_id in _root_text_id_cache:
        return _root_text_id_cache[cbeta_id]
    row = (
        await db.execute(
            sql_text("SELECT id FROM buddhist_texts WHERE cbeta_id = :c AND lang = 'lzh' LIMIT 1"),
            {"c": cbeta_id},
        )
    ).first()
    tid = row[0] if row else None
    _root_text_id_cache[cbeta_id] = tid
    return tid


async def _inject_root_sutra_slot(
    db: AsyncSession, query: str, query_embedding: list[float], search_results: list[dict]
) -> list[dict]:
    """Reserve a context slot for the foundational text the query is about.

    Two-tier detection, mirroring the two cases of the 本经召回缺口:
      1. Named sutra (Case 1): user explicitly names a root sutra → its best
         chunk takes slot #1 (the user asked for THIS text).
      2. Doctrine term (Case 2): no sutra named, but the query contains a
         curated doctrine term (空性, 唯识, …) → the foundational treatise's
         best chunk takes the LAST slot. It belongs in context, but the user
         didn't name it, so it must not displace the reranked top hits.
    No-op when neither fires or the root is already present.

    Attribution by canonical phrase ("「色不异空」出自哪部经?") joins tier 1: the
    quoted line IS the answer's source, so its root takes slot #1 like a named one."""
    named = _detect_named_root(query) or _detect_phrase_root(query)
    cbeta_id = named or _detect_doctrine_root(query)
    if not cbeta_id:
        return search_results
    root_tid = await _resolve_root_text_id(db, cbeta_id)
    if root_tid is None:
        return search_results
    if any(r["text_id"] == root_tid for r in search_results):
        return search_results
    root_hits = await similarity_search(db, query_embedding, limit=1, scope_text_ids=[root_tid])
    if not root_hits:
        return search_results
    others = [r for r in search_results if r["text_id"] != root_tid]
    if named:
        logger.debug("本经召回保底: slot #1 for named root %s (text_id=%d)", cbeta_id, root_tid)
        # Root keeps its raw cosine (lower than the others' blended rerank
        # scores); it sits at slot 1 by construction — do NOT re-sort after this.
        return [root_hits[0], *others[: MAX_CONTEXT_CHUNKS - 1]]
    logger.debug("义理本典保底: last slot for doctrine root %s (text_id=%d)", cbeta_id, root_tid)
    return [*others[: MAX_CONTEXT_CHUNKS - 1], root_hits[0]]


def _format_source_label(result: dict) -> str:
    if result.get("title_zh"):
        return f"《{result['title_zh']}》第{result['juan_num']}卷"
    return f"文本#{result['text_id']} 第{result['juan_num']}卷"


def _merge_with_alignment_sync(lzh_hits: list[dict], pi_hits: list[dict], bo_hits: list[dict]) -> list[dict]:
    """Merge per-language RAG hits into a single score-ranked list.

    Called in place of a single similarity_search when ENABLE_PARALLEL_RAG is on.
    Primary source (highest-ranked lzh) is preserved; pi/bo hits are interleaved
    by score so the LLM gets a cross-canon sampling. Alignment parallels are
    attached later in _attach_parallel_chunks, not here — keeps responsibilities
    separated.
    """
    merged: list[dict] = []
    merged.extend(lzh_hits)
    merged.extend(pi_hits)
    merged.extend(bo_hits)
    merged.sort(key=lambda r: r["score"], reverse=True)
    return merged


async def _attach_parallel_chunks(db: AsyncSession, results: list[dict]) -> None:
    """For each result in-place, populate its parallel_chunks via alignment_pairs.

    Looks up alignment_pairs for the (text_id, juan_num, chunk_index) tuple in
    both directions (text_a and text_b sides). For each match, fetches the
    aligned chunk's text from text_embeddings + title_zh from buddhist_texts.

    Implementation note: collapses the previous N+1 (1 alignment query per
    primary + 1 chunk-text query per parallel — up to 25 sequential awaits at
    5×5) into a single bulk SQL round-trip. Builds two CTEs:
      1. `primaries(idx, tid, juan, cidx)` — VALUES table of input tuples
      2. ranked alignment matches per primary, joined back to text_embeddings
         + buddhist_texts in one shot
    Then groups results in Python by primary index. Modifies `results` in
    place by setting result["parallel_chunks"] to a list of
    ParallelChunk-compatible dicts.
    """
    if not results:
        return
    for r in results:
        r.setdefault("parallel_chunks", [])
    try:
        # Build a VALUES list parametrized by primary index so we can match
        # alignment rows back to the right result. Index is 0-based.
        primary_keys: list[tuple[int, int, int, int]] = [
            (i, int(r["text_id"]), int(r["juan_num"]), int(r["chunk_index"])) for i, r in enumerate(results)
        ]
        # Construct the VALUES clause inline (small N, all integers — safe to
        # interpolate). Each row is `(idx, tid, juan, cidx)`.
        values_sql = ", ".join(f"({idx}, {tid}, {juan}, {cidx})" for idx, tid, juan, cidx in primary_keys)
        # Single bulk query:
        #   - primaries: input tuples with their original index
        #   - matches: alignment_pairs joined with primaries in either direction,
        #              returning the OTHER side
        #   - ranked: top-5 per primary by confidence
        #   - final: join ranked with text_embeddings + buddhist_texts to fetch
        #            chunk_text + title
        bulk_sql = sql_text(f"""
            WITH primaries(idx, tid, juan, cidx) AS (
                VALUES {values_sql}
            ),
            matches AS (
                SELECT
                    p.idx AS primary_idx,
                    CASE WHEN ap.text_a_id = p.tid AND ap.text_a_juan_num = p.juan AND ap.text_a_chunk_index = p.cidx
                         THEN ap.text_b_id ELSE ap.text_a_id END AS other_text_id,
                    CASE WHEN ap.text_a_id = p.tid AND ap.text_a_juan_num = p.juan AND ap.text_a_chunk_index = p.cidx
                         THEN ap.text_b_juan_num ELSE ap.text_a_juan_num END AS other_juan,
                    CASE WHEN ap.text_a_id = p.tid AND ap.text_a_juan_num = p.juan AND ap.text_a_chunk_index = p.cidx
                         THEN ap.text_b_chunk_index ELSE ap.text_a_chunk_index END AS other_chunk_idx,
                    CASE WHEN ap.text_a_id = p.tid AND ap.text_a_juan_num = p.juan AND ap.text_a_chunk_index = p.cidx
                         THEN ap.text_b_lang ELSE ap.text_a_lang END AS other_lang,
                    ap.confidence
                FROM primaries p
                JOIN alignment_pairs ap ON (
                    (ap.text_a_id = p.tid AND ap.text_a_juan_num = p.juan AND ap.text_a_chunk_index = p.cidx)
                    OR
                    (ap.text_b_id = p.tid AND ap.text_b_juan_num = p.juan AND ap.text_b_chunk_index = p.cidx)
                )
                WHERE ap.text_a_chunk_index IS NOT NULL
            ),
            ranked AS (
                SELECT m.*,
                       ROW_NUMBER() OVER (PARTITION BY m.primary_idx ORDER BY m.confidence DESC) AS rn
                FROM matches m
            )
            SELECT
                r.primary_idx,
                r.other_text_id,
                r.other_juan,
                r.other_chunk_idx,
                r.other_lang,
                r.confidence,
                te.chunk_text,
                COALESCE(bt.title_zh, bt.title_sa, bt.title_pi, bt.title_en, '') AS title
            FROM ranked r
            LEFT JOIN text_embeddings te
                ON te.text_id = r.other_text_id
               AND te.juan_num = r.other_juan
               AND te.chunk_index = r.other_chunk_idx
            LEFT JOIN buddhist_texts bt ON bt.id = r.other_text_id
            WHERE r.rn <= 5
            ORDER BY r.primary_idx, r.rn
        """)
        rows = (await db.execute(bulk_sql)).fetchall()
        for row in rows:
            primary_idx = row[0]
            chunk_text = row[6]
            # Skip parallels that have no chunk_text (LEFT JOIN miss) — matches
            # original behavior which only appended when the per-row fetch hit.
            if chunk_text is None:
                continue
            results[primary_idx]["parallel_chunks"].append(
                {
                    "text_id": row[1],
                    "juan_num": row[2],
                    "chunk_index": row[3],
                    "chunk_text": chunk_text,
                    "lang": row[4] or "lzh",
                    "title": row[7],
                    "confidence": float(row[5]),
                }
            )
    except Exception:
        logger.exception("Failed to attach parallel chunks")


def _format_context_block(result: dict) -> str:
    """Format a single RAG result into the LLM context string.

    Adds [跨藏对读] annotations when parallel_chunks are present, so the LLM
    knows it has cross-canon evidence available for the citation.
    """
    header = f"[出处: {_format_source_label(result)}]"
    body = result["chunk_text"]
    parallels = result.get("parallel_chunks") or []
    if parallels:
        parallel_lines = []
        for p in parallels[:3]:  # cap at 3 parallels per primary source
            lang_label = {"pi": "巴利", "bo": "藏", "sa": "梵", "en": "英", "lzh": "汉"}.get(p["lang"], p["lang"])
            title = p.get("title", "") or "其他藏经"
            parallel_lines.append(f"  · [{lang_label}] 《{title}》 第{p['juan_num']}卷: {p['chunk_text'][:300]}")
        parallel_block = "\n[跨藏对读 parallel_chunks]\n" + "\n".join(parallel_lines)
        return f"{header}\n{body}{parallel_block}"
    return f"{header}\n{body}"


def _keyword_rerank(query: str, results: list[dict]) -> list[dict]:
    """Re-score results using keyword overlap + vector similarity.

    Works without any external API (zero-config improvement).
    Combines:
      - Original vector cosine similarity (70% weight)
      - Character-level keyword overlap between query and chunk (20% weight)
      - Title match boost when query mentions a specific sutra name (10% weight)
    """
    query_chars = set(query)
    for r in results:
        chunk_chars = set(r["chunk_text"][:500])
        keyword_overlap = len(query_chars & chunk_chars) / max(len(query_chars), 1)

        # Title boost: check if any multi-char segment of the title appears in query
        title_boost = 0.0
        title = r.get("title_zh", "")
        if title:
            # Extract meaningful segments (2+ chars) from title for matching
            for i in range(len(title)):
                for length in range(2, min(len(title) - i + 1, 8)):
                    segment = title[i : i + length]
                    if segment in query:
                        title_boost = 1.0
                        break
                if title_boost > 0:
                    break

        original_score = r["score"]
        r["score"] = original_score * 0.7 + keyword_overlap * 0.2 + title_boost * 0.1
        logger.debug(
            "Rerank [keyword]: text_id=%s juan=%s | vec=%.3f kw=%.3f title=%.1f -> final=%.3f",
            r["text_id"],
            r["juan_num"],
            original_score,
            keyword_overlap,
            title_boost,
            r["score"],
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


async def _api_rerank(query: str, results: list[dict]) -> list[dict]:
    """Re-score results using an external cross-encoder reranker API.

    Uses the Jina/BAAI reranker API format (compatible with SiliconFlow, Jina, etc.).
    Falls back to keyword reranking on failure.
    """
    api_url = settings.reranker_api_url
    api_key = settings.reranker_api_key or settings.embedding_api_key or settings.llm_api_key
    model = settings.reranker_model

    # Cap how many docs we cross-encode: bounds latency/cost and the request
    # body even if a future caller widens the candidate pool. Today the pool is
    # ~15-20 after dedup, well under this; results beyond it keep vector-only
    # score (api defaults to 0.0 below) and rank last.
    documents = [r["chunk_text"][:500] for r in results[:RERANK_CANDIDATE_LIMIT]]

    try:
        # Short timeout: the keyword fallback is cheap and local, so don't make a
        # reranker hiccup cost the user 15s of dead air on an interactive query.
        async with httpx.AsyncClient(timeout=6) as client:
            resp = await client.post(
                f"{api_url}/rerank",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "query": query,
                    "documents": documents,
                    "top_n": len(documents),
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # API returns: {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
        rerank_scores = {item["index"]: item["relevance_score"] for item in data["results"]}

        for i, r in enumerate(results):
            original_score = r["score"]
            api_score = rerank_scores.get(i, 0.0)
            # Blend: 40% vector similarity + 60% cross-encoder score
            r["score"] = original_score * 0.4 + api_score * 0.6
            logger.debug(
                "Rerank [API]: text_id=%s juan=%s | vec=%.3f api=%.3f -> final=%.3f",
                r["text_id"],
                r["juan_num"],
                original_score,
                api_score,
                r["score"],
            )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    except Exception:
        logger.warning("API reranker failed, falling back to keyword reranking", exc_info=True)
        return _keyword_rerank(query, results)


async def _rerank(query: str, results: list[dict]) -> list[dict]:
    """Rerank results using API cross-encoder if configured, else keyword-based."""
    if not results:
        return results

    t0 = time.monotonic()

    if settings.reranker_api_url:
        reranked = await _api_rerank(query, results)
        logger.debug("TIMING: API reranking took %.2fs (%d chunks)", time.monotonic() - t0, len(results))
    else:
        reranked = _keyword_rerank(query, results)
        logger.debug("TIMING: Keyword reranking took %.2fs (%d chunks)", time.monotonic() - t0, len(results))

    return reranked


_s2t = OpenCC("s2t")
_t2s = OpenCC("t2s")

# Maximum dictionary definitions to include in RAG context
MAX_DICT_ENTRIES = 3
# Maximum characters per dictionary definition
MAX_DICT_DEF_CHARS = 200

# Pattern to extract CJK terms (2-8 chars) from user message
_CJK_TERM_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]{2,8}")
# Common question words to strip before extracting terms
_QUESTION_WORDS = re.compile(
    r"什么是|是什么|什么叫|什么意思|怎么理解|如何理解|何谓|何为|"
    r"请问|请解释|解释一下|介绍一下|简述|详解|含义|意思|概念|定义|"
    r"的意思|是指|指的是|讲的是|说的是"
)


def _zh_variants(q: str) -> list[str]:
    """Return deduplicated [original, simplified, traditional] variants."""
    return list({q, _t2s.convert(q), _s2t.convert(q)})


async def _lookup_dictionary_terms(db: AsyncSession, query: str) -> str:
    """Look up Buddhist dictionary entries matching terms in the user query.

    Extracts CJK terms from the query and searches for exact headword matches,
    falling back to prefix matches. Returns formatted text block or empty string.
    """
    # Strip common question words to isolate the actual term
    cleaned = _QUESTION_WORDS.sub("", query).strip()
    # Extract candidate terms from cleaned query (CJK sequences of 2-8 chars)
    terms = _CJK_TERM_RE.findall(cleaned)
    # Also try the original query as fallback
    if not terms:
        terms = _CJK_TERM_RE.findall(query)
    if not terms:
        return ""

    # Deduplicate while preserving order, limit to first 5 terms
    seen: set[str] = set()
    unique_terms: list[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)
        if len(unique_terms) >= 5:
            break

    # Collect all variants for all terms
    all_variants: list[str] = []
    for term in unique_terms:
        all_variants.extend(_zh_variants(term))
    all_variants = list(set(all_variants))

    try:
        # Phase 1: exact headword match
        exact_conds = [DictionaryEntry.headword == v for v in all_variants]
        stmt = (
            select(DictionaryEntry)
            .where(or_(*exact_conds))
            .options(joinedload(DictionaryEntry.source))
            .limit(MAX_DICT_ENTRIES)
        )
        result = await db.execute(stmt)
        entries = list(result.unique().scalars().all())

        # Phase 2: prefix match if exact found too few
        if len(entries) < MAX_DICT_ENTRIES:
            prefix_conds = [DictionaryEntry.headword.startswith(v) for v in all_variants]
            seen_ids = {e.id for e in entries}
            stmt2 = (
                select(DictionaryEntry)
                .where(or_(*prefix_conds))
                .options(joinedload(DictionaryEntry.source))
                .limit(MAX_DICT_ENTRIES)
            )
            result2 = await db.execute(stmt2)
            for e in result2.unique().scalars().all():
                if e.id not in seen_ids and len(entries) < MAX_DICT_ENTRIES:
                    entries.append(e)
                    seen_ids.add(e.id)

        if not entries:
            return ""

        # Format dictionary entries
        lines: list[str] = []
        for e in entries:
            source_name = e.source.name_zh if e.source else "未知辞典"
            definition = (e.definition or "")[:MAX_DICT_DEF_CHARS]
            if e.definition and len(e.definition) > MAX_DICT_DEF_CHARS:
                definition += "…"
            lines.append(f"「{e.headword}」—— {source_name}：{definition}")

        return "【辞典参考】\n" + "\n".join(lines)

    except Exception:
        logger.warning("Dictionary lookup failed, skipping", exc_info=True)
        return ""


async def retrieve_rag_context(
    db: AsyncSession,
    query: str,
    *,
    prev_query: str | None = None,
    pgvector_limit: int = 15,
    scope_text_ids: list[int] | None = None,
) -> tuple[list[ChatSource], str]:
    """Run pgvector similarity search and return (sources, context_text).

    Pipeline:
      1. Embed query → pgvector HNSW top-K retrieval
      2. Filter by MIN_RELEVANCE_SCORE, dedupe by (text_id, juan_num)
      3. Rerank (keyword-based or API cross-encoder)
      4. Cap at MAX_CONTEXT_CHUNKS (5) results

    When prev_query is provided (from conversation history), it is prepended
    to the current query for embedding generation, enabling context-aware
    retrieval in multi-turn conversations.
    """
    sources: list[ChatSource] = []
    context_text = ""
    t0 = time.monotonic()

    # Precise retrieval short-circuit: when the user explicitly names a
    # 《经名》第N卷 we go to text_contents directly. Vector retrieval
    # over 678K chunks can return thematically-similar passages from the
    # wrong text — and the LLM has no signal that the user asked for a
    # specific fascicle. Returns None unless the pattern is unambiguous
    # AND the title resolves to exactly one buddhist_texts row AND that
    # fascicle has non-empty content; on any miss we fall through to
    # vector RAG below.
    try:
        precise = await try_precise_text_retrieval(
            db, query, scope_text_ids=scope_text_ids,
        )
    except Exception:
        logger.exception("precise_retrieval failed; falling back to vector RAG")
        precise = None
    if precise:
        logger.debug("precise_retrieval hit: %d source(s)", len(precise))
        context_text = "\n\n".join(_format_context_block({
            "text_id": s.text_id,
            "juan_num": s.juan_num,
            "chunk_index": s.chunk_index,
            "chunk_text": s.chunk_text,
            "title_zh": s.title_zh,
            "score": s.score,
        }) for s in precise)
        return precise, context_text

    try:
        search_query = f"{prev_query} {query}" if prev_query else query
        query_embedding = await generate_embedding(search_query)
        t1 = time.monotonic()
        logger.debug("TIMING: Embedding took %.2fs", t1 - t0)

        # Text chunk retrieval: two modes depending on ENABLE_PARALLEL_RAG.
        # Asymmetric scope contract — see chat.py wiring docstring.
        # Empty list is intentionally treated as "no scope" here so
        # masters with no indexed corpus (Ajahn Chah, Hsing Yun, …) get
        # full-corpus parallel RAG; the same empty list disables
        # precise retrieval (see precise_retrieval.try_precise_text_retrieval).
        if ENABLE_PARALLEL_RAG and not scope_text_ids:
            # Per-language top-k retrieval, then alignment-aware merging.
            # scope_text_ids (master persona mode) bypasses parallel mode
            # since master's scriptures are already filtered to a specific set.
            #
            # The three language searches and the source search are mutually
            # independent (same query_embedding, no shared state), so run them
            # concurrently instead of serially. Each MUST get its own session:
            # one AsyncSession multiplexes a single asyncpg connection and
            # cannot run concurrent queries ("another operation is in progress").
            # Returned rows are plain dicts, so they stay valid after the
            # session closes. During this sub-second window an in-flight
            # /chat/stream holds up to 5 pooled connections (1 prep session +
            # 4 search) before the LLM-streaming phase releases them all
            # (pool 10+20) — fine at this site's concurrency, but watch
            # pg_stat_activity if traffic grows.
            async def _vsearch(limit, lang_list):
                async with async_session() as s:
                    return await similarity_search(
                        s, query_embedding, limit=limit, lang_list=lang_list
                    )

            async def _ssearch():
                async with async_session() as s:
                    return await source_similarity_search(
                        s, query_embedding, limit=3, min_score=0.5
                    )

            lzh_hits, pi_hits, bo_hits, source_results = await asyncio.gather(
                _vsearch(PARALLEL_LZH_K, ["lzh"]),
                _vsearch(PARALLEL_PI_K, ["pi"]),
                _vsearch(PARALLEL_BO_K, ["bo"]),
                _ssearch(),
            )
            text_results = _merge_with_alignment_sync(lzh_hits, pi_hits, bo_hits)
        else:
            text_results = await similarity_search(
                db, query_embedding, limit=pgvector_limit, scope_text_ids=scope_text_ids
            )
            source_results = await source_similarity_search(db, query_embedding, limit=3, min_score=0.5)

        logger.debug("TIMING: pgvector search took %.2fs", time.monotonic() - t1)

        # Filter out low-relevance chunks and deduplicate by (text_id, juan_num)
        seen = set()
        filtered = []
        for r in text_results:
            if r["score"] < MIN_RELEVANCE_SCORE:
                continue
            key = (r["text_id"], r["juan_num"])
            if key in seen:
                continue
            seen.add(key)
            filtered.append(r)

        # Rerank filtered results
        reranked = await _rerank(query, filtered)

        # Cap at MAX_CONTEXT_CHUNKS (fewer but more relevant after reranking)
        search_results = reranked[:MAX_CONTEXT_CHUNKS]

        # 本经召回保底: if the user named a root sutra, guarantee it a context
        # slot — vector recall + rerank otherwise bury the terse root under its
        # own dense commentaries. Full-corpus mode only; master personas keep
        # their scoped corpus untouched. Isolated so a hiccup in the extra
        # similarity_search degrades to the un-injected top-5 rather than
        # bubbling to the outer rollback and wiping a good answer.
        if not scope_text_ids:
            try:
                search_results = await _inject_root_sutra_slot(
                    db, query, query_embedding, search_results
                )
            except Exception:
                logger.warning("本经召回保底 injection failed; using un-injected results", exc_info=True)

        # Attach alignment parallels to sources (only if parallel mode on).
        # Query alignment_pairs for each primary hit; if found, inject the
        # aligned chunks' text into parallel_chunks for downstream use.
        if ENABLE_PARALLEL_RAG and search_results:
            await _attach_parallel_chunks(db, search_results)

        sources = [
            ChatSource(**{k: v for k, v in r.items() if k not in ("source_id",)} | {"source_id": r.get("source_id")})
            for r in search_results
        ]
        context_parts = [_format_context_block(r) for r in search_results]
        context_text = "\n\n".join(context_parts)

        # Append source recommendations if any matched
        if source_results:
            logger.debug(
                "Found %d relevant data sources (scores: %s)",
                len(source_results),
                [f"{s['name_zh']}={s['score']:.3f}" for s in source_results],
            )
            source_lines = []
            for s in source_results:
                desc = (s["description"] or "")[:80]
                url = s["base_url"] or ""
                source_lines.append(f"- {s['name_zh']}：{desc}（{url}）")
            context_text += "\n\n[相关数据源推荐]\n" + "\n".join(source_lines)

        # Dictionary term lookup for authoritative definitions
        t_dict = time.monotonic()
        dict_text = await _lookup_dictionary_terms(db, query)
        if dict_text:
            context_text += "\n\n" + dict_text
            logger.debug("TIMING: Dictionary lookup took %.2fs", time.monotonic() - t_dict)
    except Exception:
        logger.exception("Embedding/search failed, proceeding without RAG context")
        await db.rollback()

    logger.debug("TIMING: Total RAG retrieval took %.2fs (results: %d)", time.monotonic() - t0, len(sources))
    return sources, context_text
