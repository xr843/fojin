/**
 * Remove the server-rendered `<link rel="canonical">` before React mounts.
 *
 * Every shell ships one (index.html says `https://fojin.app/`; per-route and
 * backend shells say their own URL). react-helmet-async does not replace it —
 * it appends its own `data-rh` tag — so after hydration the rendered DOM carried
 * two canonicals, and on SPA-fallback routes they disagreed (`/` vs the page).
 * Search engines that render JS treat conflicting canonicals as no signal at all.
 *
 * Crawlers that don't run JS still read the server tag from the raw HTML; for
 * the rendered DOM the page's own <Helmet> is the single source. Pages that set
 * no canonical end up with none, which beats a wrong one.
 */
export function dropServerCanonical(doc: Document = document): void {
  doc.head.querySelectorAll('link[rel="canonical"]:not([data-rh])').forEach((el) => el.remove());
}
