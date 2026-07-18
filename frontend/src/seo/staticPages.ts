/**
 * Build-time SEO shells for key routes: `seoPages()` in vite.config.ts stamps
 * these into per-route dist/<route>/index.html so crawlers get the right
 * title/description/noscript without executing JS.
 *
 * Kept out of vite.config.ts so the copy is unit-testable against the runtime
 * <Helmet> strings in public/locales — the two drifted apart before (the
 * /collections shell described a feature that no longer exists).
 *
 * The copy itself lives in staticPages.json (data, not code): these are
 * build-time crawler meta, deliberately NOT run through the i18n runtime, so
 * keeping them out of a .ts source also keeps them out of the hardcoded-Chinese
 * ratchet (scan-hardcoded-zh.mjs scans .ts/.tsx, not .json) without polluting
 * the zero-debt baseline.
 */
import pages from "./staticPages.json";

export interface SeoPage {
  title: string;
  desc: string;
  noscript: string;
}

export const STATIC_SEO_PAGES: Record<string, SeoPage> = pages;
