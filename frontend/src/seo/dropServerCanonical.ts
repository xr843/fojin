import { langUrl, type SeoLang } from "./langUrl";

/**
 * Remove a server-rendered `<link rel="canonical">` that names a different page.
 *
 * react-helmet-async appends its own `data-rh` canonical instead of replacing
 * the shell's, so after hydration the DOM can carry two. On SPA-fallback routes
 * (e.g. /map) the shell's says `https://fojin.app/` — a different page — and
 * search engines that render JS treat conflicting canonicals as no signal.
 *
 * A shell canonical that already equals this page's URL in this language is
 * kept: pages like /chat set no canonical in <Helmet>, and the shell's is right.
 */
export function dropServerCanonical(pathname: string, lang: SeoLang, doc: Document = document): void {
  const expected = langUrl(pathname, lang);
  doc.head.querySelectorAll('link[rel="canonical"]:not([data-rh])').forEach((el) => {
    if (el.getAttribute("href") !== expected) el.remove();
  });
}
