/**
 * Per-language URLs for crawler-facing tags (canonical / hreflang / og:url).
 *
 * FoJin serves three UI languages from one path, distinguished only by
 * `?lang=`. Each variant must self-canonicalise and cross-reference the others,
 * or search engines fold them into the simplified page. The server emits the
 * same tags (backend/app/services/seo_lang.py, the build-time shells, the
 * sitemap) — these functions must produce byte-identical URLs.
 * See docs/superpowers/specs/2026-10-11-i18n-seo-design.md.
 *
 * ⚠️ main.tsx 静态导入本文件：这里不得引入 OpenCC（utils/hanScript，约 550 KB 压缩），
 * 否则每个页面首屏都会先下载整套繁简词库。需要繁简转换的放 seoTitle.ts。
 */
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
