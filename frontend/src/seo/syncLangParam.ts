import { toSeoLang } from "./langUrl";

/**
 * The location search after switching the UI to `lang`: `?lang=` set for
 * zh-Hant / en, removed for zh, every other param kept. The language switcher
 * applies it through React Router's `navigate(…, { replace: true })` — not raw
 * `history.replaceState` — so the router's own location includes it and a later
 * `setSearchParams` on the same page doesn't silently drop it again.
 */
export function searchWithLang(search: string, lang: string): string {
  const params = new URLSearchParams(search);
  const seo = toSeoLang(lang);
  if (seo === "zh") params.delete("lang");
  else params.set("lang", seo);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}
