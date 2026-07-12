"""Sentence-level cross-canon alignment core (Package C).

Three concerns, cleanly separated so the hard part is unit-testable without a
DB or an embedding API:

1. ``split_sentences`` — pure, deterministic, offset-preserving sentence
   splitter. Chinese (lzh/zh) splits on 。！？；and closing 」』; other languages
   split on ``[.!?;]`` and newlines. Every :class:`Sentence` carries offsets
   RELATIVE to the passed text plus ``base_offset``, so a caller can map a
   sentence straight back into the full juan's ``text_contents.content``.

2. ``align_sentences`` — the bertalign-core dynamic program over a PRECOMPUTED
   cosine-similarity matrix. No embeddings inside, so it unit-tests on synthetic
   matrices. ``cosine_matrix`` is the pure helper that builds that matrix.

3. ``embed_and_align`` — the only I/O: batch-embed both sides via
   :func:`app.services.embedding.generate_embeddings_batch`, build the cosine
   matrix, run the DP, map the winning indices back to offset spans.

Nothing here imports numpy/scipy/faiss/bertalign — the DP is plain Python.

Tunables are module constants (calibrate against human labels before any read
path trusts them; see the batch job docstring):

* ``GAP_PENALTY`` — cost of skipping one sentence on either side in the DP.
  Higher → the aligner prefers to align even weak pairs rather than skip; lower
  → it drops more sentences as unaligned. 0.5 sits just below a plausible true
  cross-lingual BGE-M3 cosine so a real match always beats skipping both sides
  (adds ``s`` vs ``-2·GAP``), while a spurious ~0.3 pair is still cheaper to
  align-then-post-filter than to force a skip.
* ``MIN_SENTENCE_SIMILARITY`` — pairs whose averaged cosine is below this are
  dropped AFTER the DP (bertalign's post-filter): the DP finds the best
  monotonic path, then genuinely unrelated pairs on that path are discarded.
  0.65 keeps confident 汉↔外文 pairs; prod data showed the 0.4–0.6 band was
  overwhelmingly spurious while hand-verified good parallels score ≥0.75.
* ``MAX_SENTENCES_PER_CHUNK`` — guard on the O(m·n) DP / embedding batch. Chunk
  pairs are paragraph-sized (rarely >~40 sentences a side); a side past this cap
  is refused rather than risk a pathological run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.services.embedding import generate_embeddings_batch

# ── tunables (module constants, not config.py) ──────────────────────────────
GAP_PENALTY = 0.5
# Raised 0.4 → 0.65 after prod data (2026-07-12): 97% of 汉↔外文 cross-lingual
# pairs scored 0.4–0.6 and were mostly spurious; hand-verified good parallels
# score ≥0.75 ("佛說如是。"↔"That is what the Buddha said" = 0.81). 0.65 keeps
# confident pairs and drops the low-signal flood.
MIN_SENTENCE_SIMILARITY = 0.65
MAX_SENTENCES_PER_CHUNK = 200
# Drop degenerate "sentences" — bare punctuation ("。") or a 1-char stub ("身。")
# that the splitter emits from punctuation-dense verse and which produced garbage
# alignments. Counts alnum chars only (letters / CJK ideographs / digits).
MIN_MEANINGFUL_SENTENCE_CHARS = 2

# Chinese sentence terminators and the closing quotes that terminate / attach to
# the preceding sentence. Opening 「『 are deliberately NOT boundaries, so nested
# quotes do not spuriously split a sentence.
_ZH_ENDERS = "。！？；"
_ZH_CLOSERS = "」』"
_ZH_BOUNDARY = frozenset(_ZH_ENDERS + _ZH_CLOSERS)

# Latin-script / other languages: sentence punctuation plus hard newlines.
_LATIN_ENDERS = ".!?;"
_OTHER_BOUNDARY = frozenset(_LATIN_ENDERS + "\n")

_ZH_LANGS = frozenset({"lzh", "zh", "zh-hant", "zh-hans"})


@dataclass(frozen=True, slots=True)
class Sentence:
    """One sentence with offsets into the source text (already ``base_offset``
    adjusted, so they map straight back into the full juan)."""

    char_start: int
    char_end: int
    text: str


@dataclass(frozen=True, slots=True)
class AlignedPair:
    """One aligned sentence pair, offsets absolute in each side's source."""

    align_type: str  # '1-1' | '1-2' | '2-1'
    a_char_start: int
    a_char_end: int
    sent_a_text: str
    b_char_start: int
    b_char_end: int
    sent_b_text: str
    similarity: float


# ── 1. splitter ─────────────────────────────────────────────────────────────


def _boundary_for(lang: str | None) -> frozenset[str]:
    return _ZH_BOUNDARY if (lang or "").lower() in _ZH_LANGS else _OTHER_BOUNDARY


def _emit(out: list[Sentence], text: str, start: int, end: int, base_offset: int) -> None:
    """Append text[start:end] as a Sentence, trimming surrounding whitespace by
    moving the offsets INWARD so they stay exact (text == source[s:e]). Empty /
    whitespace-only spans are skipped."""
    s, e = start, end
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    if e <= s:
        return
    # Skip degenerate fragments (bare punctuation / single stray char) — they are
    # noise for cross-lingual alignment. Count content chars (alnum), not punct.
    if sum(1 for c in text[s:e] if c.isalnum()) < MIN_MEANINGFUL_SENTENCE_CHARS:
        return
    out.append(Sentence(char_start=base_offset + s, char_end=base_offset + e, text=text[s:e]))


def split_sentences(text: str, lang: str, *, base_offset: int = 0) -> list[Sentence]:
    """Split ``text`` into sentences, preserving exact offsets.

    A boundary run (one or more consecutive terminator/closer chars, e.g. ``。」``
    or ``?!`` or ``.\\n``) ends the current sentence and attaches ALL of the run
    to it. A trailing fragment with no terminator becomes its own sentence, so an
    unpunctuated text yields exactly one sentence covering the whole string.
    Offsets are relative to ``text`` plus ``base_offset``; whitespace at a
    sentence's edges is trimmed by adjusting offsets inward (never by rewriting
    the string), and empty/whitespace-only spans are dropped.
    """
    boundary = _boundary_for(lang)
    out: list[Sentence] = []
    n = len(text)
    seg_start = 0
    i = 0
    while i < n:
        # Cut only at the END of a boundary run so consecutive terminators and
        # closing quotes stay attached to the sentence they close.
        if text[i] in boundary and (i + 1 >= n or text[i + 1] not in boundary):
            _emit(out, text, seg_start, i + 1, base_offset)
            seg_start = i + 1
        i += 1
    if seg_start < n:
        _emit(out, text, seg_start, n, base_offset)
    return out


# ── 2. cosine matrix + bertalign-core DP ────────────────────────────────────


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def cosine_matrix(rows: list[list[float]], cols: list[list[float]]) -> list[list[float]]:
    """Cosine-similarity matrix ``sim[i][j]`` between ``rows`` (source) and
    ``cols`` (target) vectors, clamped to [-1, 1]. A zero-norm or
    mismatched-length vector yields 0.0 for that cell (no meaningful angle)."""
    row_norms = [_norm(r) for r in rows]
    col_norms = [_norm(c) for c in cols]
    out: list[list[float]] = []
    for i, r in enumerate(rows):
        ri = row_norms[i]
        line: list[float] = []
        for j, c in enumerate(cols):
            cj = col_norms[j]
            if ri == 0.0 or cj == 0.0 or len(r) != len(c):
                line.append(0.0)
                continue
            dot = sum(x * y for x, y in zip(r, c, strict=True))
            line.append(max(-1.0, min(1.0, dot / (ri * cj))))
        out.append(line)
    return out


# A backtrack step: (prev_i, prev_j, emitted_pair_or_None) where an emitted pair
# is (align_type, src_index_tuple, tgt_index_tuple, averaged_score).
_Pair = tuple[str, tuple[int, ...], tuple[int, ...], float]
_Step = tuple[int, int, _Pair | None]


def align_sentences(
    sim: list[list[float]],
    *,
    gap_penalty: float = GAP_PENALTY,
    min_similarity: float = MIN_SENTENCE_SIMILARITY,
) -> list[_Pair]:
    """Monotonic sentence alignment over a precomputed cosine matrix ``sim``
    (rows = source sentences, cols = target sentences).

    Dynamic program. ``dp[i][j]`` is the best total score aligning the first
    ``i`` source and first ``j`` target sentences. The recurrence maximizes over
    five monotonic moves into ``(i, j)`` (all strictly increase ``i + j``, so a
    single forward pass in increasing (i, j) sees every predecessor first):

        dp[i][j] = max(
            dp[i-1][j-1] + sim[i-1][j-1],                              # 1-1
            dp[i-1][j-2] + avg(sim[i-1][j-2], sim[i-1][j-1]),          # 1-2
            dp[i-2][j-1] + avg(sim[i-2][j-1], sim[i-1][j-1]),          # 2-1
            dp[i-1][j]   - gap_penalty,                                # skip src
            dp[i][j-1]   - gap_penalty,                                # skip tgt
        )

    with ``dp[0][0] = 0``. Backtracking from ``dp[m][n]`` recovers the path;
    skip moves emit no pair. Finally every emitted pair whose averaged score is
    ``< min_similarity`` is dropped (bertalign's post-filter: the DP still lays
    down the best monotonic path, then genuinely unrelated pairs are discarded).
    Returns ``[(align_type, src_indices, tgt_indices, score), ...]`` in source
    order. Empty inputs → ``[]``.
    """
    m = len(sim)
    n = len(sim[0]) if m else 0
    if m == 0 or n == 0:
        return []

    neg_inf = float("-inf")
    dp = [[neg_inf] * (n + 1) for _ in range(m + 1)]
    back: list[list[_Step | None]] = [[None] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = 0.0

    for i in range(m + 1):
        for j in range(n + 1):
            if i == 0 and j == 0:
                continue
            best = neg_inf
            step: _Step | None = None

            # skip source sentence i-1
            if i >= 1 and dp[i - 1][j] > neg_inf:
                cand = dp[i - 1][j] - gap_penalty
                if cand > best:
                    best, step = cand, (i - 1, j, None)
            # skip target sentence j-1
            if j >= 1 and dp[i][j - 1] > neg_inf:
                cand = dp[i][j - 1] - gap_penalty
                if cand > best:
                    best, step = cand, (i, j - 1, None)
            # 1-1
            if i >= 1 and j >= 1 and dp[i - 1][j - 1] > neg_inf:
                score = sim[i - 1][j - 1]
                cand = dp[i - 1][j - 1] + score
                if cand > best:
                    best, step = cand, (i - 1, j - 1, ("1-1", (i - 1,), (j - 1,), score))
            # 1-2: source i-1 aligned with targets j-2, j-1
            if i >= 1 and j >= 2 and dp[i - 1][j - 2] > neg_inf:
                score = (sim[i - 1][j - 2] + sim[i - 1][j - 1]) / 2
                cand = dp[i - 1][j - 2] + score
                if cand > best:
                    best, step = cand, (i - 1, j - 2, ("1-2", (i - 1,), (j - 2, j - 1), score))
            # 2-1: sources i-2, i-1 aligned with target j-1
            if i >= 2 and j >= 1 and dp[i - 2][j - 1] > neg_inf:
                score = (sim[i - 2][j - 1] + sim[i - 1][j - 1]) / 2
                cand = dp[i - 2][j - 1] + score
                if cand > best:
                    best, step = cand, (i - 2, j - 1, ("2-1", (i - 2, i - 1), (j - 1,), score))

            dp[i][j] = best
            back[i][j] = step

    # Backtrack from (m, n) collecting emitted pairs (skips emit nothing).
    pairs: list[_Pair] = []
    i, j = m, n
    while (i, j) != (0, 0):
        step = back[i][j]
        if step is None:  # pragma: no cover - dp[0][0] is the only None-back cell
            break
        prev_i, prev_j, pair = step
        if pair is not None:
            pairs.append(pair)
        i, j = prev_i, prev_j
    pairs.reverse()

    return [p for p in pairs if p[3] >= min_similarity]


def sentence_align_key(
    text_a_id: int,
    text_a_juan_num: int,
    text_a_char_start: int,
    text_b_id: int,
    text_b_juan_num: int,
    text_b_char_start: int,
) -> tuple[int, int, int, int, int, int]:
    """The uq_sentence_align identity of a row — used to dedup a write batch
    in-memory before ``INSERT ... ON CONFLICT DO NOTHING`` (matches the DB
    unique constraint exactly, so both agree on what "the same pair" is)."""
    return (
        text_a_id, text_a_juan_num, text_a_char_start,
        text_b_id, text_b_juan_num, text_b_char_start,
    )


# ── 3. embedding glue (the only I/O) ────────────────────────────────────────


async def embed_and_align(
    src_sents: list[Sentence],
    tgt_sents: list[Sentence],
    *,
    gap_penalty: float = GAP_PENALTY,
    min_similarity: float = MIN_SENTENCE_SIMILARITY,
    embed_fn=None,
) -> list[AlignedPair]:
    """Embed both sentence lists (ONE batched API call), align them, and map the
    winning indices back to offset spans.

    Returns [] for an empty side or a side past ``MAX_SENTENCES_PER_CHUNK`` (the
    caller counts the guard hit). ``embed_fn`` is injectable for tests; it
    defaults to the platform's multilingual BGE-M3 batch client. Merged sides
    (1-2 / 2-1) span from the first constituent's start to the last's end;
    ``sent_text`` is the constituent sentence texts joined by a space — the
    offset span remains the source of truth for an exact re-slice.
    """
    if not src_sents or not tgt_sents:
        return []
    if len(src_sents) > MAX_SENTENCES_PER_CHUNK or len(tgt_sents) > MAX_SENTENCES_PER_CHUNK:
        return []
    if embed_fn is None:
        embed_fn = generate_embeddings_batch

    src_texts = [s.text for s in src_sents]
    tgt_texts = [t.text for t in tgt_sents]
    vectors = await embed_fn(src_texts + tgt_texts)
    if len(vectors) != len(src_texts) + len(tgt_texts):
        return []
    src_vecs = vectors[: len(src_texts)]
    tgt_vecs = vectors[len(src_texts):]

    sim = cosine_matrix(src_vecs, tgt_vecs)
    aligned = align_sentences(sim, gap_penalty=gap_penalty, min_similarity=min_similarity)

    out: list[AlignedPair] = []
    for align_type, src_idx, tgt_idx, score in aligned:
        a_first, a_last = src_sents[src_idx[0]], src_sents[src_idx[-1]]
        b_first, b_last = tgt_sents[tgt_idx[0]], tgt_sents[tgt_idx[-1]]
        out.append(AlignedPair(
            align_type=align_type,
            a_char_start=a_first.char_start,
            a_char_end=a_last.char_end,
            sent_a_text=" ".join(src_sents[k].text for k in src_idx),
            b_char_start=b_first.char_start,
            b_char_end=b_last.char_end,
            sent_b_text=" ".join(tgt_sents[k].text for k in tgt_idx),
            similarity=score,
        ))
    return out
