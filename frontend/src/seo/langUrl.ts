/**
 * Per-language URLs for crawler-facing tags (canonical / hreflang / og:url).
 *
 * FoJin serves three UI languages from one path, distinguished only by
 * `?lang=`. Each variant must self-canonicalise and cross-reference the others,
 * or search engines fold them into the simplified page. The server emits the
 * same tags (backend/app/services/seo_lang.py, the build-time shells, the
 * sitemap) — these functions must produce byte-identical URLs.
 * See docs/superpowers/specs/2026-10-11-i18n-seo-design.md.
 */
import { localizeHan } from "../utils/hanScript";

export type SeoLang = "zh" | "zh-Hant" | "en";

const ORIGIN = "https://fojin.app";

export function toSeoLang(lng: string): SeoLang {
  const l = lng.toLowerCase();
  if (l.startsWith("zh-hant")) return "zh-Hant";
  if (l === "en" || l.startsWith("en-")) return "en";
  return "zh";
}

export function langUrl(path: string, lang: SeoLang): string {
  const url = `${ORIGIN}${path}`;
  return lang === "zh" ? url : `${url}?lang=${lang}`;
}

const OG_LOCALE: Record<SeoLang, string> = { zh: "zh_CN", "zh-Hant": "zh_TW", en: "en_US" };

export function ogLocaleFor(lang: SeoLang): string {
  return OG_LOCALE[lang];
}

/**
 * Sutra titles are stored in traditional script. The simplified page shows
 * 「简体（繁體）」— same rule as the server's `localize_title`, so the title a
 * JS-rendering crawler sees matches the one in the served HTML.
 */
export function seoTitle(title: string, lang: SeoLang): string {
  if (lang !== "zh" || !title) return title;
  const simplified = localizeHan(title, "zh");
  return simplified === title ? title : `${simplified}（${title}）`;
}
