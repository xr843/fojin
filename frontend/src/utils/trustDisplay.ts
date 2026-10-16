import type { ChatTrustStatus } from "../api/client";

/** i18n key of the one-line aggregate trust label under an answer (and atop the
 *  citation side panel). null = the answer carries no trust status. */
export function trustStatusLabelKey(status?: ChatTrustStatus | null): string | null {
  if (!status) return null;
  return `chat.trust.${status.state}`;
}

export function trustStatusColor(status?: ChatTrustStatus | null): string {
  switch (status?.state) {
    case "verified":
      return "var(--fj-success)";
    case "quote_relaxed":
      // A paraphrase-as-quote was relaxed to prose (fixed) — a correction, not
      // a warning, so use the accent tone rather than the legacy amber.
      return "var(--fj-accent)";
    case "quote_unverified":
      return "#a66300";
    case "no_sources":
      return "var(--fj-ink-muted)";
    default:
      return "var(--fj-accent)";
  }
}
