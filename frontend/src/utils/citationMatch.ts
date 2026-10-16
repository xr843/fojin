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
 * usually simplified, so every comparison folds 繁→简 first. That fold does NOT
 * preserve UTF-16 indices (compatibility ideographs are surrogate pairs that
 * fold to one unit), so findQuoteSpan folds per code point and keeps a raw map.
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
    // chunk_text is required by the ChatSource type, but history messages come
    // back from chat_messages.sources — persisted JSON that no runtime check
    // validates, and rows written before the field existed simply lack it.
    // Throwing here would blank the whole message, so skip what we can't match.
    if (!s.chunk_text) continue;
    if (normalizeForMatch(s.chunk_text).includes(nq)) {
      if (!best || s.score > best.score) best = s;
    }
  }
  return best;
}

// Per-code-point fold cache. Folding one code point at a time (rather than the
// whole string) is what lets us keep an exact raw-index map: OpenCC is NOT
// length-preserving in UTF-16 units — CBETA uses compatibility ideographs such
// as 灰 U+2F835 (a surrogate pair) that it folds to U+7070 (one unit). Three of
// those before a quote shifted the drawer highlight three characters early
// (《楞伽經宗通》卷7, 2026-10-16).
const _foldCache = new Map<string, string>();
function foldChar(ch: string): string {
  let f = _foldCache.get(ch);
  if (f === undefined) {
    f = toSimplified(ch);
    _foldCache.set(ch, f);
  }
  return f;
}

/** Folded text plus, for every folded UTF-16 unit, the raw [start, end) of the
 *  code point it came from. */
function foldWithMap(raw: string): { folded: string; starts: number[]; ends: number[] } {
  let folded = "";
  const starts: number[] = [];
  const ends: number[] = [];
  let r = 0;
  for (const ch of raw) {
    const f = foldChar(ch);
    folded += f;
    for (let k = 0; k < f.length; k++) {
      starts.push(r);
      ends.push(r + ch.length);
    }
    r += ch.length;
  }
  return { folded, starts, ends };
}

function foldPlain(s: string): string {
  let out = "";
  for (const ch of s) out += foldChar(ch);
  return out;
}

/**
 * Locate the quoted passage inside a rendered chunk so the drawer can <mark>
 * it. Returns [start, end) indices into the original `haystack`, or null.
 *
 * Folds both sides 繁→简 code point by code point, keeping a map back to raw
 * indices, for a direct substring hit; if punctuation differs between the LLM
 * quote and the CBETA text (or CBETA hard-wraps inside it), retries on a
 * punctuation-stripped projection and maps the hit back the same way.
 */
export function findQuoteSpan(
  haystack: string,
  quote: string,
): [number, number] | null {
  const { folded: hs, starts, ends } = foldWithMap(haystack);
  const qs = foldPlain(quote).trim();
  if (qs.length < 4) return null;

  const direct = hs.indexOf(qs);
  if (direct >= 0) return [starts[direct], ends[direct + qs.length - 1]];

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
  // The stripped match ends on the last Han character; carry the quote's own
  // closing punctuation (「…佛法。」) along when the source has the same marks
  // there, hard-wraps aside, so the highlight covers exactly what was quoted.
  let last = map[sIdx + qStripped.length - 1];
  const tail = qs.slice(qs.replace(new RegExp(PUNCT_ONE.source + "+$"), "").length);
  let k = last + 1;
  for (const tc of tail) {
    while (k < hs.length && /\s/.test(hs[k])) k++;
    if (hs[k] !== tc) break;
    last = k;
    k++;
  }
  return [starts[map[sIdx]], ends[last]];
}


// 省略号的三种写法：中文双省略号、单省略号、以及 ASCII 三点。
const ELLIPSIS = /(?:…{1,2}|\.{3,})/;

/** 与 findQuoteSpan 自身的下限一致（4 字）。另立一个更严的门槛只会让
 *  「說名非白」这类合法短句无声地标不出来。 */
const MIN_FRAGMENT_CHARS = 4;

/**
 * Locate a quoted passage, tolerating the ellipses an LLM uses to abridge it.
 *
 * `findQuoteSpan` needs the quote to be one contiguous run. Models routinely
 * write 「於無學法說純白聲……以無漏業非順愛故」, where the elided middle means no
 * such run exists — the match fails and the drawer falls back to tinting the
 * whole ~500-char chunk, whose edges sit on arbitrary ingestion cut points. That
 * reads as a highlighting bug (prod report 2026-07-29), and it is avoidable:
 * each fragment on its own does occur, verbatim.
 *
 * Fragments are matched left to right and each search resumes after the previous
 * hit, so the spans come back ordered, non-overlapping, and in the source's own
 * order — an abridged quote cannot be highlighted out of sequence.
 */
export function findQuoteSpans(
  haystack: string,
  quote: string | undefined,
): [number, number][] {
  if (!quote) return [];
  const whole = findQuoteSpan(haystack, quote);
  if (whole) return [whole];

  const fragments = quote
    .split(ELLIPSIS)
    .map((f) => f.trim())
    .filter((f) => f.length >= MIN_FRAGMENT_CHARS);
  if (fragments.length === 0) return [];

  const spans: [number, number][] = [];
  let cursor = 0;
  for (const fragment of fragments) {
    const hit = findQuoteSpan(haystack.slice(cursor), fragment);
    if (!hit) continue;
    spans.push([cursor + hit[0], cursor + hit[1]]);
    cursor += hit[1];
  }
  return spans;
}
