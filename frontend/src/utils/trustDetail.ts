import type { ChatTrustStatus } from "../api/client";

/**
 * An optional, honest clarification shown next to the trust badge about how
 * many 「…」 quotes were actually verbatim-checked.
 *
 * The green "引用已校验" badge is awarded for a citation existing — it does NOT
 * mean a verbatim quote was checked. `quote_checked_count` disambiguates:
 *  - a positive count → say how many quotes checked out;
 *  - zero on a green "verified" answer → say plainly that it quoted nothing
 *    verbatim, so the badge stops implying a quote was verified;
 *  - null/undefined → a historical answer whose count was never stored, or no
 *    status at all → show nothing.
 * Other states (`quote_relaxed`, `sources_available`, …) already describe
 * themselves, so a zero count there would only add noise.
 */
export type QuoteCheckDetail =
  | { key: "chat.trust.quotes_checked"; count: number }
  | { key: "chat.trust.no_verbatim_quote" };

export function quoteCheckDetail(
  status?: ChatTrustStatus | null,
): QuoteCheckDetail | null {
  if (!status) return null;
  const n = status.quote_checked_count;
  if (n == null) return null;
  if (n > 0) return { key: "chat.trust.quotes_checked", count: n };
  if (status.state === "verified") return { key: "chat.trust.no_verbatim_quote" };
  return null;
}
