import type { ChatCheckedQuote, ChatMessageItem, ChatSource } from "../api/client";
import type { CitationTarget } from "../components/CitationDrawer";
import { CITATION_URL_SCHEME, injectCitationLinks, parseCitationHref } from "./citationLinks";
import { normalizeForMatch } from "./citationMatch";

/** One explicit 【《经名》第N卷】 citation of an answer, as the side panel lists it. */
export interface AnswerCitation {
  key: string;
  /** Exactly what clicking the same citation inline opens. */
  target: CitationTarget;
  /** True ONLY when the backend listed this very passage (same title, same
   *  quoted text) in trust_status.checked_quotes — i.e. the verifier compared it
   *  verbatim against the cited fascicle and it held. Never inferred. */
  verbatimChecked: boolean;
}

// The explicit-marker links injectCitationLinks emits: label starts with 【.
// Bare 《title》 mentions (its pass 2) are prose name-drops, not citations.
const EXPLICIT_LINK_RE = new RegExp(
  String.raw`\[(【[^\]]*】)\]\((${CITATION_URL_SCHEME}://[^)\s]*)\)`,
  "g",
);

function isCheckedQuote(
  checked: ChatCheckedQuote[] | null | undefined,
  titleZh: string,
  quote: string | undefined,
): boolean {
  if (!checked || checked.length === 0 || !quote) return false;
  const nt = normalizeForMatch(titleZh);
  const nq = normalizeForMatch(quote);
  if (!nq) return false;
  return checked.some((c) => normalizeForMatch(c.title) === nt && normalizeForMatch(c.quote) === nq);
}

/**
 * The explicit citations of one answer, in order, deduplicated. Built by running
 * the SAME link injection the inline renderer uses and reading its links back, so
 * a panel row and the inline link it mirrors always open the same passage.
 */
export function extractAnswerCitations(
  content: string,
  sources: ChatSource[] | null,
  language: string,
  checked?: ChatCheckedQuote[] | null,
): AnswerCitation[] {
  if (!content || !sources || sources.length === 0) return [];
  const linked = injectCitationLinks(content, sources, language);
  const out: AnswerCitation[] = [];
  const seen = new Set<string>();
  for (const m of linked.matchAll(EXPLICIT_LINK_RE)) {
    const parsed = parseCitationHref(m[2]);
    if (!parsed) continue;
    const key = `${parsed.textId}:${parsed.juanNum}:${parsed.chunkIndex}:${parsed.quote ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      key,
      target: parsed,
      verbatimChecked: isCheckedQuote(checked, parsed.titleZh, parsed.quote),
    });
  }
  return withUnshownCheckedQuotes(out, content, checked);
}

/**
 * The inline link carries only the quote nearest its 【】 marker, but the
 * verifier may have checked a different 「…」 in the same passage (prod session
 * 3652: 「已逐字核验 3 条」 next to 1 badge). Give every checked quote that no row
 * shows its own badged row, right after the citation of the same title and
 * fascicle, so the badges add up to the count. Only quotes that really occur in
 * the answer, under a fascicle the answer really cites — never invented.
 */
function withUnshownCheckedQuotes(
  rows: AnswerCitation[],
  content: string,
  checked: ChatCheckedQuote[] | null | undefined,
): AnswerCitation[] {
  if (!checked || checked.length === 0 || rows.length === 0) return rows;
  const nContent = normalizeForMatch(content);
  const shown = new Set(
    rows.filter((r) => r.target.quote).map((r) => `${normalizeForMatch(r.target.titleZh)}|${normalizeForMatch(r.target.quote!)}`),
  );
  const out = [...rows];
  for (const c of checked) {
    const nq = normalizeForMatch(c.quote);
    const nt = normalizeForMatch(c.title);
    if (!nq || shown.has(`${nt}|${nq}`) || !nContent.includes(nq)) continue;
    const anchor = out.findIndex(
      (r) => normalizeForMatch(r.target.titleZh) === nt && (c.juan == null || r.target.juanNum === c.juan),
    );
    if (anchor < 0) continue;
    const base = out[anchor].target;
    let at = anchor + 1;
    while (at < out.length && out[at].target.textId === base.textId && out[at].target.juanNum === base.juanNum) at++;
    out.splice(at, 0, {
      key: `${base.textId}:${base.juanNum}:${base.chunkIndex}:${c.quote}`,
      target: { ...base, quote: c.quote },
      verbatimChecked: true,
    });
    shown.add(`${nt}|${nq}`);
  }
  return out;
}

/** Retrieved sources deduplicated by (text, fascicle) — same rule as the
 *  「参考经文」 chips under an answer. */
export function distinctSourceFascicles(sources: ChatSource[] | null | undefined): ChatSource[] {
  if (!sources) return [];
  const seen = new Set<string>();
  const out: ChatSource[] = [];
  for (const s of sources) {
    if (!s.title_zh) continue;
    const key = `${s.text_id}:${s.juan_num}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}

/** How many distinct texts (部) the answer's retrieval drew on. */
export function distinctSourceTextCount(sources: ChatSource[] | null | undefined): number {
  if (!sources) return 0;
  return new Set(sources.filter((s) => s.text_id > 0).map((s) => s.text_id)).size;
}

function sameTarget(a: CitationTarget, b: CitationTarget): boolean {
  return (
    a.textId === b.textId &&
    a.juanNum === b.juanNum &&
    a.chunkIndex === b.chunkIndex &&
    (a.quote ?? "") === (b.quote ?? "")
  );
}

/**
 * Which assistant answer a just-opened citation belongs to. `preferred` is
 * checked first (a panel click always belongs to the panel's own answer), then
 * answers newest-first. Matches the answer's explicit citations, then its
 * retrieved sources (chip clicks carry no quote). null = not found.
 */
export function findAnswerForTarget(
  messages: ChatMessageItem[],
  target: CitationTarget,
  language: string,
  preferred?: ChatMessageItem | null,
): ChatMessageItem | null {
  const owns = (m: ChatMessageItem): boolean => {
    if (m.role !== "assistant") return false;
    if (extractAnswerCitations(m.content, m.sources, language).some((c) => sameTarget(c.target, target))) {
      return true;
    }
    return (m.sources ?? []).some(
      (s) =>
        s.text_id === target.textId &&
        s.juan_num === target.juanNum &&
        (s.chunk_index ?? -1) === target.chunkIndex,
    );
  };
  if (preferred && owns(preferred)) return preferred;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (owns(messages[i])) return messages[i];
  }
  return null;
}
