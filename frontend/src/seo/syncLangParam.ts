import { toSeoLang } from "./langUrl";

/**
 * After a UI language switch, write `?lang=` into the address bar (zh removes
 * it) so a link copied or shared afterwards opens in the same language — and
 * matches the per-language canonical the page now declares.
 *
 * `replaceState` with the current `history.state` kept intact: React Router
 * stores its own entry key there, and dropping it breaks back/forward.
 */
export function syncLangParam(lang: string, loc: Location = window.location, hist: History = window.history): void {
  const url = new URL(loc.href);
  const seo = toSeoLang(lang);
  if (seo === "zh") url.searchParams.delete("lang");
  else url.searchParams.set("lang", seo);
  const qs = url.searchParams.toString();
  hist.replaceState(hist.state, "", `${url.pathname}${qs ? `?${qs}` : ""}${url.hash}`);
}
