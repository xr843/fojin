/**
 * Quote-aware citation matching.
 *
 * The RAG pipeline retrieves several chunks per cited text. The old citation
 * wiring keyed a citation to the *highest-scored* chunk for a title, which is
 * rarely the chunk that actually holds the sentence the LLM quoted — so
 * clicking a citation opened a passage that did not contain the quote.
 *
 * These helpers locate the chunk whose text genuinely contains the quoted
 * passage, and (for the drawer) the quote's span inside that text so it can
 * be highlighted. CBETA stores traditional Chinese while LLM answers are
 * usually simplified, so every comparison folds 繁→简 first. That fold is
 * 1 char → 1 char, which preserves string indices — findQuoteSpan depends on
 * that to map a match on the folded text back onto the original.
 */
import * as OpenCC from "opencc-js";

import type { ChatSource } from "../api/client";

const _t2s = OpenCC.Converter({ from: "tw", to: "cn" });

export function toSimplified(s: string): string {
  try {
    return _t2s(s);
  } catch {
    return s;
  }
}

// Punctuation + whitespace stripped before substring tests so a dropped or
// swapped comma does not break matching. Mirrors the backend quote verifier's
// _STRIP_PUNCT_RE. `g` flag — only use with .replace(), not .test().
// \u3000 is the ideographic (full-width) space — written as an escape so
// ESLint's no-irregular-whitespace does not trip on a literal in source.
const PUNCT_GLOBAL =
  /[\s,.!?;:"'()[\]\-_~`<>*，。！？、；：「」『』“”‘’《》〈〉…—（）【】·•～\u3000]/g;
const PUNCT_ONE =
  /[\s,.!?;:"'()[\]\-_~`<>*，。！？、；：「」『』“”‘’《》〈〉…—（）【】·•～\u3000]/;

/** Fold 繁→简, strip punctuation/whitespace, lowercase — for tolerant matching. */
export function normalizeForMatch(s: string): string {
  return toSimplified(s).replace(PUNCT_GLOBAL, "").toLowerCase();
}

// A 「…」/『…』/“…”/‘…’/"…" pair sitting within ~80 chars before a citation
// marker — the passage the LLM is attributing. Mirrors the backend verifier's
// _QUOTE_CITATION_RE lookback window.
const PRECEDING_QUOTE_RE =
  /[「『“‘"]([^「『“‘"」』”’]{6,400})[」』”’"][^【】「『“‘"」』”’]{0,80}$/;

/** Pull the quoted passage that sits just before a citation marker, if any. */
export function extractPrecedingQuote(textBefore: string): string | null {
  const m = textBefore.slice(-520).match(PRECEDING_QUOTE_RE);
  return m ? m[1].trim() : null;
}

/**
 * Among the retrieved chunks for a cited title, pick the one whose text
 * actually contains the quoted passage. Returns null when no chunk does
 * (genuine hallucination, or a quote spanning a chunk boundary) — callers
 * fall back to the top-scored chunk.
 */
export function pickSourceForQuote(
  candidates: ChatSource[],
  quote: string | null,
): ChatSource | null {
  if (!quote) return null;
  const nq = normalizeForMatch(quote);
  if (nq.length < 6) return null;
  let best: ChatSource | null = null;
  for (const s of candidates) {
    if (s.chunk_index == null) continue;
    if (normalizeForMatch(s.chunk_text).includes(nq)) {
      if (!best || s.score > best.score) best = s;
    }
  }
  return best;
}

/**
 * Locate the quoted passage inside a rendered chunk so the drawer can <mark>
 * it. Returns [start, end) indices into the original `haystack`, or null.
 *
 * Folds both sides 繁→简 (index-preserving) for a direct substring hit; if
 * punctuation differs between the LLM quote and the CBETA text, retries on a
 * punctuation-stripped projection and maps the hit back to original indices.
 */
export function findQuoteSpan(
  haystack: string,
  quote: string,
): [number, number] | null {
  const hs = toSimplified(haystack);
  const qs = toSimplified(quote).trim();
  if (qs.length < 4) return null;

  const direct = hs.indexOf(qs);
  if (direct >= 0) return [direct, direct + qs.length];

  // Punctuation-tolerant pass: strip punct from both, match, map back.
  const qStripped = qs.replace(PUNCT_GLOBAL, "");
  if (qStripped.length < 4) return null;
  const map: number[] = [];
  let stripped = "";
  for (let i = 0; i < hs.length; i++) {
    if (!PUNCT_ONE.test(hs[i])) {
      map.push(i);
      stripped += hs[i];
    }
  }
  const sIdx = stripped.indexOf(qStripped);
  if (sIdx < 0) return null;
  return [map[sIdx], map[sIdx + qStripped.length - 1] + 1];
}

/**
 * Locate the quote across a sequence of rendered blocks and return, per block,
 * the [start, end) slice to highlight (or null).
 *
 * The citation drawer splits the passage into leading-context / center /
 * trailing blocks, and chunks overlap by 50 chars — so a sentence sitting on
 * a chunk boundary ends up straddling two blocks after de-overlap. Searching
 * the concatenated text and mapping the hit back per block highlights the
 * whole sentence even when it crosses a block boundary.
 */
export function mapQuoteToBlocks(
  blockTexts: string[],
  quote: string | undefined,
): ([number, number] | null)[] {
  const result: ([number, number] | null)[] = blockTexts.map(() => null);
  if (!quote) return result;
  const span = findQuoteSpan(blockTexts.join(""), quote);
  if (!span) return result;
  let offset = 0;
  for (let i = 0; i < blockTexts.length; i++) {
    const blockStart = offset;
    const blockEnd = offset + blockTexts[i].length;
    offset = blockEnd;
    const s = Math.max(span[0], blockStart);
    const e = Math.min(span[1], blockEnd);
    if (s < e) result[i] = [s - blockStart, e - blockStart];
  }
  return result;
}
