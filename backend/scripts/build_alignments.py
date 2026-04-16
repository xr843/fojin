"""Build chunk-level cross-canon alignments for FoJin 三语 RAG MVP.

Pipeline per (text_a, text_b) pair:

    for chunk in text_a.chunks:
        candidates = pgvector top-20 of text_b chunks by cosine distance to chunk.vec
        for cand in candidates:
            verdict = llm_verify(chunk.text, cand.text, a_lang, b_lang)
            if verdict.confidence >= CONFIDENCE_THRESHOLD and verdict.is_parallel:
                insert alignment_pairs(chunk, cand, confidence, method='embed_llm')

Usage:
    # Dry-run: embedding recall only, no LLM calls, print sample candidates
    python -m scripts.build_alignments --pair heart --dry-run

    # Full run on a single MVP pair
    python -m scripts.build_alignments --pair heart

    # Full run on all 5 MVP pairs
    python -m scripts.build_alignments --pair all

    # Run with cap on chunks per text (for smoke test)
    python -m scripts.build_alignments --pair heart --limit-chunks 10

    # Override confidence threshold (default 0.75)
    python -m scripts.build_alignments --pair all --threshold 0.85

Guards:
    - Hardcoded cost ceiling $50 — script aborts if estimated LLM spend exceeds
    - Idempotent: unique index uq_align_chunk_pair prevents duplicate inserts
    - Resolves text_ids from DB at runtime by (cbeta_id | title pattern, source code)
    - All 5 MVP pairs' resolution keys are defined below in MVP_PAIRS
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import async_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Config
# ============================================================================

CONFIDENCE_THRESHOLD = 0.75          # only persist pairs with LLM confidence >= this
EMBED_TOP_K = 20                     # pgvector candidates per source chunk
MAX_PARALLEL_PER_CHUNK = 3           # stop after accepting this many targets for one src chunk
COST_CEILING_USD = 50.0              # abort if estimated LLM spend exceeds
AVG_TOKENS_PER_CALL = 500            # for cost estimation

# Verification LLM configuration.
# Defaults: reuse FoJin's main LLM (settings.llm_api_url + llm_model), detect
# Anthropic-vs-OpenAI format purely from URL. Override via env VERIFY_LLM_*.
VERIFY_LLM_API_URL = os.environ.get("VERIFY_LLM_API_URL", "")  # falls back to settings.llm_api_url
VERIFY_LLM_API_KEY = os.environ.get("VERIFY_LLM_API_KEY", "")  # falls back to settings.llm_api_key
VERIFY_LLM_MODEL = os.environ.get("VERIFY_LLM_MODEL", "")      # falls back to settings.llm_model

# Price per 1K tokens for cost ceiling (approximate; doesn't affect routing)
LLM_PRICE_PER_1K = {
    "claude-haiku-4-5-20251001": 0.0008,
    "gpt-4o-mini": 0.00015,
    "qwen-plus": 0.0004,
    "deepseek-chat": 0.00027,    # FoJin's current main LLM (DeepSeek V3)
    "deepseek-reasoner": 0.0014,
}
DEFAULT_PRICE_PER_1K = 0.0008    # unknown model → use Haiku estimate


# ============================================================================
# MVP pairs: (key, text_a_resolver, text_b_resolver, pair_name, desc)
# text_a is always the primary source (汉文 for user-facing narrative).
# ============================================================================

@dataclass
class TextResolver:
    """How to find text_id(s) in buddhist_texts table.

    When resolve_all=True, returns ALL matching texts as a list (multi-target).
    Used for SC Dhammapada which is stored as 26 separate vagga rows.
    """
    source_code: str
    cbeta_id: str | None = None
    cbeta_id_like: str | None = None   # ILIKE pattern for multi-target
    title_zh_like: str | None = None
    title_pi_ilike: str | None = None
    title_sa_ilike: str | None = None
    title_en_ilike: str | None = None
    text_id: int | None = None          # direct bypass — skip resolution
    resolve_all: bool = False           # if True, return all matches


@dataclass
class AlignmentPair:
    """One MVP alignment job.

    text_a is the OUTER loop (smaller text). We iterate over text_a chunks
    and for each chunk, pgvector-search top-K candidates inside text_b's
    embeddings, then LLM-verify each candidate. This keeps LLM call count
    proportional to the smaller side (O(|a| × K)) instead of O(|a| × |b|).

    UX note: "primary language for display" is handled later by the RAG
    retrieval layer's _merge_with_alignment — the data pipeline direction
    here is purely a cost-optimization concern.
    """
    key: str
    name: str
    text_a: TextResolver   # smaller / outer loop
    text_b: TextResolver   # larger / pgvector index side (may be multi-target)
    description: str
    # Optional constraint: only process text_a chunks where juan_num matches.
    # Used for 汉文 阿含 where we want e.g. only 中阿含 卷 24 (念处经卷), not full 60 juan.
    text_a_juan_filter: list[int] | None = None


# ============================================================================
# MVP pairs — verified against production DB 2026-04-15 (Day 0)
#
# Key decision: direction inverted for pairs 2+3 — the Pali/Tibetan target is
# very small relative to full CBETA 阿含 (14-52 chunks vs 1400-2900), so we
# treat Pali/Tibetan as text_a to minimize outer-loop chunk count.
# ============================================================================

MVP_PAIRS: list[AlignmentPair] = [
    AlignmentPair(
        key="heart",
        name="心经 汉藏",
        # T0251 (text_id=9) has corrupted ingestion — only 明太祖御制序 + 唐慧忠序，
        # 260-char 心经正文缺失. Using T0252 法月译广本 instead (2 chunks, 865 chars,
        # includes 「观自在菩萨」opening and full 色空 section).
        text_a=TextResolver(source_code="cbeta", text_id=10),     # T0252, 2 chunks
        text_b=TextResolver(source_code="84000", text_id=5175),   # Toh 21, 34 chunks
        description="T0252《普遍智藏般若波罗蜜多心经》法月译广本 ↔ 84000 Toh 21 藏译",
    ),
    AlignmentPair(
        key="satipatthana",
        name="念处经 巴汉",
        text_a=TextResolver(source_code="suttacentral", text_id=273),  # MN 10, 52 chunks
        text_b=TextResolver(source_code="cbeta", text_id=2),            # T0026 中阿含, 2902 chunks
        description="MN 10 Satipaṭṭhāna Sutta ↔ T0026 中阿含《念处经》卷 (embedding recall 会收敛到念处经段)",
    ),
    AlignmentPair(
        key="dhammacakka",
        name="转法轮经 巴汉",
        text_a=TextResolver(source_code="suttacentral", text_id=2207),  # SN 56.11, 14 chunks
        text_b=TextResolver(source_code="cbeta", text_id=3),             # T0099 杂阿含, 1427 chunks
        description="SN 56.11 Dhammacakkappavattana ↔ T0099 杂阿含《转法轮经》",
    ),
    AlignmentPair(
        key="dhamma_pali",
        name="法句经 汉巴",
        text_a=TextResolver(source_code="cbeta", text_id=6467),  # T0210, 47 chunks
        # Multi-target: all 26 SC Dhammapada vaggas (text_ids 3779-3804, ~139 chunks)
        text_b=TextResolver(
            source_code="suttacentral",
            cbeta_id_like="SC-dhp%",
            resolve_all=True,
        ),
        description="T0210《法句经》↔ SC Dhammapada 26 vaggas (multi-target)",
    ),
    AlignmentPair(
        key="vimalakirti",
        name="维摩诘经 汉藏",
        text_a=TextResolver(source_code="cbeta", text_id=28),      # T0475 罗什译, 81 chunks
        text_b=TextResolver(source_code="84000", text_id=5330),    # Toh 176, 711 chunks
        description="T0475《维摩诘所说经》罗什译 ↔ 84000 Toh 176 藏译",
    ),
    # ========================================================================
    # v1.1 阿含 ↔ Nikāya 全量扩展 (2026-04-16)
    # text_a is multi-target via resolve_all=True. process_pair iterates each
    # resolved Pali sutta as its own outer loop, sharing the single 汉文 阿含
    # text_b for pgvector candidate search. Idempotent across runs (uq index).
    # ========================================================================
    AlignmentPair(
        key="agama_mn",
        name="MN 152 全量 ↔ 中阿含",
        text_a=TextResolver(
            source_code="suttacentral",
            cbeta_id_like="SC-mn%",
            resolve_all=True,
        ),
        text_b=TextResolver(source_code="cbeta", text_id=2),  # T0026 中阿含
        description="所有 MN 152 部巴利经 ↔ T0026 中阿含 (~4995 outer-loop chunks)",
    ),
    AlignmentPair(
        key="agama_dn",
        name="DN 34 全量 ↔ 长阿含",
        text_a=TextResolver(
            source_code="suttacentral",
            cbeta_id_like="SC-dn%",
            resolve_all=True,
        ),
        text_b=TextResolver(source_code="cbeta", text_id=1),  # T0001 长阿含
        description="所有 DN 34 部巴利经 ↔ T0001 长阿含 (~2910 outer-loop chunks)",
    ),
    AlignmentPair(
        key="agama_sn56",
        name="SN 56 谛相应 ↔ 杂阿含",
        text_a=TextResolver(
            source_code="suttacentral",
            cbeta_id_like="SC-sn56%",
            resolve_all=True,
        ),
        text_b=TextResolver(source_code="cbeta", text_id=3),  # T0099 杂阿含
        description="SN 56 谛相应 (含转法轮经，~30 suttas) ↔ T0099 杂阿含",
    ),
    AlignmentPair(
        key="agama_an4",
        name="AN 4 四集 ↔ 增一阿含",
        text_a=TextResolver(
            source_code="suttacentral",
            cbeta_id_like="SC-an4%",
            resolve_all=True,
        ),
        text_b=TextResolver(source_code="cbeta", text_id=4),  # T0125 增壹阿含
        description="AN 4 四法集 (~270 suttas, chunks≥5 后 ~150) ↔ T0125 增壹阿含",
    ),
]


# ============================================================================
# LLM verification prompt
# ============================================================================

LANG_NAMES = {
    "lzh": "文言文（汉译佛典）",
    "pi": "巴利语",
    "sa": "梵语",
    "bo": "藏语",
    "en": "英文翻译",
}

VERIFY_SYSTEM_PROMPT = (
    "You are a Buddhist philology expert assisting with cross-canon text alignment. "
    "Given two text segments from different Buddhist canons in different languages, "
    "judge whether they are parallel passages — i.e. whether they express "
    "substantially the same teaching, narrative, or doctrinal content, even if "
    "wording differs due to translation style, compression, or expansion. "
    "\n\n"
    "Output STRICT JSON with these fields:\n"
    "  is_parallel: boolean\n"
    "  confidence: float between 0.0 and 1.0\n"
    "  reason: one short sentence (≤ 40 chars) in Chinese, explaining the judgment\n"
    "\n"
    "Return nothing except the JSON object. Be strict: if you are unsure, "
    'return is_parallel=false with confidence around 0.3. A strong match means '
    "shared doctrinal terms, same narrative sequence, or clear one-to-one "
    "semantic correspondence. A weak match is only surface-level topical similarity."
)


def build_verify_user_message(
    src_text: str, tgt_text: str, src_lang: str, tgt_lang: str
) -> str:
    return (
        f"Source ({LANG_NAMES.get(src_lang, src_lang)}):\n{src_text}\n\n"
        f"Target ({LANG_NAMES.get(tgt_lang, tgt_lang)}):\n{tgt_text}\n\n"
        'Return JSON only: {"is_parallel": bool, "confidence": float, "reason": str}'
    )


# ============================================================================
# LLM client (copied pattern from chat.py:704, kept self-contained)
# ============================================================================

async def llm_verify_pair(
    client: httpx.AsyncClient,
    src_text: str,
    tgt_text: str,
    src_lang: str,
    tgt_lang: str,
) -> dict[str, Any]:
    """Call LLM to judge whether two segments are parallel. Returns dict or raises."""
    api_url = VERIFY_LLM_API_URL or settings.llm_api_url
    api_key = VERIFY_LLM_API_KEY or settings.llm_api_key
    model = VERIFY_LLM_MODEL or settings.llm_model

    user_msg = build_verify_user_message(src_text, tgt_text, src_lang, tgt_lang)

    # URL-based provider detection (matches chat.py:_is_anthropic pattern).
    if "anthropic.com" in api_url:
        resp = await client.post(
            f"{api_url}/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "system": VERIFY_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_msg}],
                "max_tokens": 300,
                "temperature": 0.0,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
    else:
        resp = await client.post(
            f"{api_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 300,
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    # Tolerant JSON parse: some models wrap in ```json fences
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
    try:
        return json.loads(stripped.strip())
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON: %s", content[:200])
        return {"is_parallel": False, "confidence": 0.0, "reason": "parse_fail"}


# ============================================================================
# DB helpers
# ============================================================================

async def resolve_texts(session, resolver: TextResolver) -> list[tuple[int, str]]:
    """Resolve a TextResolver to list of (text_id, lang).

    Returns [] if not found.
    Returns [(id, lang)] for single-target resolvers (typical case).
    Returns [(id1, lang1), (id2, lang2), ...] when resolve_all=True.
    """
    # Direct bypass: resolver specified text_id literally (verified in Day 0)
    if resolver.text_id is not None:
        result = await session.execute(
            text("SELECT id, lang, title_zh, title_pi, title_sa, "
                 "(SELECT COUNT(*) FROM text_embeddings WHERE text_id=buddhist_texts.id) AS chunks "
                 "FROM buddhist_texts WHERE id = :tid"),
            {"tid": resolver.text_id},
        )
        row = result.fetchone()
        if not row:
            logger.error("text_id=%s not found in buddhist_texts", resolver.text_id)
            return []
        logger.info(
            "Resolved direct text_id=%s lang=%s title=%s chunks=%d",
            row[0], row[1], row[2] or row[3] or row[4] or "(no title)", row[5],
        )
        return [(row[0], row[1])]

    # Pattern-based resolution
    conditions = ["ds.code = :source_code"]
    params: dict[str, Any] = {"source_code": resolver.source_code}

    if resolver.cbeta_id:
        conditions.append("bt.cbeta_id = :cbeta_id")
        params["cbeta_id"] = resolver.cbeta_id
    if resolver.cbeta_id_like:
        conditions.append("bt.cbeta_id ILIKE :cbeta_id_like")
        params["cbeta_id_like"] = resolver.cbeta_id_like
    if resolver.title_zh_like:
        conditions.append("bt.title_zh LIKE :title_zh_like")
        params["title_zh_like"] = resolver.title_zh_like
    if resolver.title_pi_ilike:
        conditions.append("bt.title_pi ILIKE :title_pi_ilike")
        params["title_pi_ilike"] = resolver.title_pi_ilike
    if resolver.title_sa_ilike:
        conditions.append("bt.title_sa ILIKE :title_sa_ilike")
        params["title_sa_ilike"] = resolver.title_sa_ilike
    if resolver.title_en_ilike:
        conditions.append("bt.title_en ILIKE :title_en_ilike")
        params["title_en_ilike"] = resolver.title_en_ilike

    # Multi-target may include full Pali nikāya (MN 152, SN 1892, AN 1408, …).
    # Cap high so v1.1 阿含 expansion fits.
    limit = 2000 if resolver.resolve_all else 5
    sql = (
        "SELECT bt.id, bt.lang, bt.title_zh, bt.title_pi, bt.title_sa, "
        "(SELECT COUNT(*) FROM text_embeddings WHERE text_id=bt.id) AS chunks "
        "FROM buddhist_texts bt "
        "JOIN data_sources ds ON ds.id = bt.source_id "
        f"WHERE {' AND '.join(conditions)} "
        f"AND (SELECT COUNT(*) FROM text_embeddings WHERE text_id=bt.id) > 0 "
        f"ORDER BY bt.id LIMIT {limit}"
    )
    result = await session.execute(text(sql), params)
    rows = result.fetchall()
    if not rows:
        return []

    if not resolver.resolve_all and len(rows) > 1:
        logger.warning(
            "Resolver matched %d texts, picking first: %s",
            len(rows),
            [(r[0], r[2] or r[3] or r[4]) for r in rows],
        )
        rows = rows[:1]

    resolved = []
    for row in rows:
        logger.info(
            "  → text_id=%s lang=%s title=%s chunks=%d",
            row[0], row[1], row[2] or row[3] or row[4] or "(no title)", row[5],
        )
        resolved.append((row[0], row[1]))
    logger.info("Resolved %s → %d text(s)", resolver.source_code, len(resolved))
    return resolved


async def fetch_chunks(
    session,
    text_id: int,
    juan_filter: list[int] | None = None,
) -> list[dict]:
    """Fetch all chunks of a text (optionally filtered by juan_num)."""
    if juan_filter:
        placeholders = ",".join(str(j) for j in juan_filter)
        sql = (
            "SELECT juan_num, chunk_index, chunk_text "
            "FROM text_embeddings WHERE text_id = :tid "
            "AND embedding IS NOT NULL "
            f"AND juan_num IN ({placeholders}) "  # nosec B608 — juans from hardcoded MVP_PAIRS
            "ORDER BY juan_num, chunk_index"
        )
    else:
        sql = (
            "SELECT juan_num, chunk_index, chunk_text "
            "FROM text_embeddings WHERE text_id = :tid "
            "AND embedding IS NOT NULL "
            "ORDER BY juan_num, chunk_index"
        )
    result = await session.execute(text(sql), {"tid": text_id})
    return [
        {"juan_num": r[0], "chunk_index": r[1], "chunk_text": r[2]}
        for r in result.fetchall()
    ]


async def vector_topk_multi_target(
    session,
    src_text_id: int,
    src_juan: int,
    src_chunk_idx: int,
    tgt_text_ids: list[int],
    k: int,
) -> list[dict]:
    """Given a source chunk, find top-K most similar chunks across one or more target texts.

    Returns list of {text_id, juan_num, chunk_index, chunk_text, score}.
    """
    if not tgt_text_ids:
        return []
    placeholders = ",".join(str(tid) for tid in tgt_text_ids)
    raw = await session.connection()
    # Note: IN list has to be inlined (pgvector <=> operator + exec_driver_sql
    # positional params don't mix well with parameterized IN lists).
    result = await raw.exec_driver_sql(
        "SELECT te_b.text_id, te_b.juan_num, te_b.chunk_index, te_b.chunk_text, "
        "1 - (te_b.embedding <=> te_a.embedding) AS score "
        "FROM text_embeddings te_a, text_embeddings te_b "
        "WHERE te_a.text_id = $1 AND te_a.juan_num = $2 AND te_a.chunk_index = $3 "
        f"AND te_b.text_id IN ({placeholders}) "  # nosec B608
        "AND te_b.embedding IS NOT NULL "
        "ORDER BY te_b.embedding <=> te_a.embedding "
        "LIMIT $4",
        (src_text_id, src_juan, src_chunk_idx, k),
    )
    return [
        {
            "text_id": r[0], "juan_num": r[1], "chunk_index": r[2],
            "chunk_text": r[3], "score": float(r[4]),
        }
        for r in result.fetchall()
    ]


async def insert_alignment(
    session,
    a_text_id: int,
    a_juan: int,
    a_idx: int,
    a_lang: str,
    b_text_id: int,
    b_juan: int,
    b_idx: int,
    b_lang: str,
    confidence: float,
    method: str = "embed_llm",
) -> None:
    """Idempotent insert to alignment_pairs. Uses uq_align_chunk_pair unique index."""
    await session.execute(
        text(
            "INSERT INTO alignment_pairs "
            "(text_a_id, text_a_juan_num, text_a_chunk_index, text_a_lang, "
            " text_b_id, text_b_juan_num, text_b_chunk_index, text_b_lang, "
            " confidence, method, created_at) "
            "VALUES (:a_id, :a_juan, :a_idx, :a_lang, "
            "        :b_id, :b_juan, :b_idx, :b_lang, "
            "        :conf, :method, NOW()) "
            "ON CONFLICT (text_a_id, text_a_juan_num, text_a_chunk_index, "
            "             text_b_id, text_b_juan_num, text_b_chunk_index) "
            "WHERE text_a_chunk_index IS NOT NULL "
            "DO NOTHING"
        ),
        {
            "a_id": a_text_id, "a_juan": a_juan, "a_idx": a_idx, "a_lang": a_lang,
            "b_id": b_text_id, "b_juan": b_juan, "b_idx": b_idx, "b_lang": b_lang,
            "conf": confidence, "method": method,
        },
    )


# ============================================================================
# Main alignment loop
# ============================================================================

class CostGuard:
    def __init__(self, ceiling_usd: float, price_per_1k: float):
        self.ceiling = ceiling_usd
        self.price_per_1k = price_per_1k
        self.total_tokens = 0

    def add(self, tokens: int) -> None:
        self.total_tokens += tokens

    def spend_usd(self) -> float:
        return (self.total_tokens / 1000.0) * self.price_per_1k

    def check(self) -> None:
        if self.spend_usd() > self.ceiling:
            raise RuntimeError(
                f"Cost ceiling ${self.ceiling:.2f} exceeded "
                f"(spent ~${self.spend_usd():.2f} on {self.total_tokens} tokens)"
            )


async def process_pair(
    pair: AlignmentPair,
    dry_run: bool,
    limit_chunks: int | None,
    threshold: float,
    cost_guard: CostGuard,
) -> dict[str, int]:
    """Process one MVP pair. Returns counters dict."""
    stats = {"accepted": 0, "rejected_llm": 0, "rejected_embed": 0, "errors": 0}

    async with async_session() as session:
        a_resolved = await resolve_texts(session, pair.text_a)
        b_resolved = await resolve_texts(session, pair.text_b)

        if not a_resolved or not b_resolved:
            logger.error(
                "❌ Pair %s: could not resolve texts (a=%s b=%s)",
                pair.key, a_resolved, b_resolved,
            )
            stats["errors"] += 1
            return stats

        # text_b may be multi-target (Dhammapada vagga case)
        b_ids = [bid for bid, _blang in b_resolved]
        b_lang_map = {bid: blang for bid, blang in b_resolved}
        b_lang_primary = b_resolved[0][1]

        # text_a may also be multi-target (v1.1 阿含 expansion: MN 152 / DN 34 etc.).
        # Iterate each resolved text_a as its own outer loop so RAM stays bounded
        # and progress can be committed per-sutta.
        logger.info(
            "▶ Pair %s: %d source text(s) (text_a) ↔ %d target text(s) (text_b, lang=%s)",
            pair.key, len(a_resolved), len(b_ids), b_lang_primary,
        )

        async with httpx.AsyncClient() as http_client:
            for a_idx, (a_id, a_lang) in enumerate(a_resolved, 1):
                a_chunks = await fetch_chunks(session, a_id, pair.text_a_juan_filter)
                if limit_chunks:
                    a_chunks = a_chunks[:limit_chunks]

                if not a_chunks:
                    continue

                logger.info(
                    "  [a:%d/%d] text_a_id=%s lang=%s — %d chunks to process",
                    a_idx, len(a_resolved), a_id, a_lang, len(a_chunks),
                )

                for i, src in enumerate(a_chunks, 1):
                    candidates = await vector_topk_multi_target(
                        session, a_id, src["juan_num"], src["chunk_index"], b_ids, EMBED_TOP_K,
                    )
                    candidates = [c for c in candidates if c["score"] >= 0.35]

                    if not candidates:
                        stats["rejected_embed"] += 1
                        continue

                    if dry_run:
                        top = candidates[0]
                        logger.info(
                            "    [%d/%d] src='%s...' → top score=%.3f tgt=text_id=%s '%s...'",
                            i, len(a_chunks),
                            src["chunk_text"][:40],
                            top["score"],
                            top["text_id"],
                            top["chunk_text"][:40],
                        )
                        continue

                    accepted_for_chunk = 0
                    for cand in candidates:
                        if accepted_for_chunk >= MAX_PARALLEL_PER_CHUNK:
                            break

                        cost_guard.add(AVG_TOKENS_PER_CALL)
                        try:
                            cost_guard.check()
                        except RuntimeError as e:
                            logger.error("🛑 %s", e)
                            await session.commit()
                            return stats

                        try:
                            verdict = await llm_verify_pair(
                                http_client, src["chunk_text"], cand["chunk_text"],
                                a_lang, b_lang_primary,
                            )
                        except (httpx.HTTPError, KeyError) as e:
                            logger.warning("LLM call failed: %s", e)
                            stats["errors"] += 1
                            continue

                        if verdict.get("is_parallel") and verdict.get("confidence", 0.0) >= threshold:
                            cand_text_id = cand["text_id"]
                            cand_lang = b_lang_map.get(cand_text_id, b_lang_primary)
                            await insert_alignment(
                                session,
                                a_id, src["juan_num"], src["chunk_index"], a_lang,
                                cand_text_id, cand["juan_num"], cand["chunk_index"], cand_lang,
                                float(verdict["confidence"]),
                            )
                            stats["accepted"] += 1
                            accepted_for_chunk += 1
                        else:
                            stats["rejected_llm"] += 1

                # Commit + progress log after each source text completes
                await session.commit()
                logger.info(
                    "  [a:%d/%d] done: ✓total=%d ✗llm=%d ✗embed=%d spent=$%.3f",
                    a_idx, len(a_resolved),
                    stats["accepted"], stats["rejected_llm"], stats["rejected_embed"],
                    cost_guard.spend_usd(),
                )

    return stats


async def main_async(pair_key: str, dry_run: bool, limit_chunks: int | None, threshold: float) -> None:
    pairs_to_run = (
        MVP_PAIRS if pair_key == "all"
        else [p for p in MVP_PAIRS if p.key == pair_key]
    )
    if not pairs_to_run:
        logger.error("❌ No MVP pair with key=%s (available: %s)",
                     pair_key, [p.key for p in MVP_PAIRS])
        sys.exit(1)

    effective_model = VERIFY_LLM_MODEL or settings.llm_model
    price = LLM_PRICE_PER_1K.get(effective_model, DEFAULT_PRICE_PER_1K)
    cost_guard = CostGuard(COST_CEILING_USD, price)
    logger.info("Using verify LLM: %s @ %s (cost est $%.5f/1K tok)",
                effective_model,
                VERIFY_LLM_API_URL or settings.llm_api_url,
                price)

    overall = {"accepted": 0, "rejected_llm": 0, "rejected_embed": 0, "errors": 0}

    for pair in pairs_to_run:
        logger.info("=" * 70)
        logger.info("Pair: %s — %s", pair.name, pair.description)
        logger.info("=" * 70)
        stats = await process_pair(pair, dry_run, limit_chunks, threshold, cost_guard)
        for k, v in stats.items():
            overall[k] += v

    logger.info("=" * 70)
    logger.info("FINAL: %s", overall)
    logger.info("Total estimated cost: $%.3f", cost_guard.spend_usd())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pair",
        required=True,
        help="Pair key: heart|satipatthana|dhammacakka|dhamma_pali|vimalakirti|agama_mn|agama_dn|agama_sn56|agama_an4|all",
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls, print embedding candidates only")
    parser.add_argument("--limit-chunks", type=int, default=None, help="Cap chunks per text (for smoke testing)")
    parser.add_argument("--threshold", type=float, default=CONFIDENCE_THRESHOLD)
    args = parser.parse_args()

    asyncio.run(main_async(args.pair, args.dry_run, args.limit_chunks, args.threshold))
