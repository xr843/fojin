import { describe, expect, it } from "vitest";
import zh from "../../public/locales/zh/translation.json";
import { STATIC_SEO_PAGES } from "./staticPages";

/**
 * The build-time SEO shells and the runtime <Helmet> are two descriptions of the
 * same page, written in two different files, and nothing kept them in sync — the
 * /collections shell still advertised a long-gone "藏经收藏 / 管理您的收藏集合"
 * personal-bookmarks feature while the live page is the curated 经典专题 index.
 * Crawlers only ever saw the stale copy.
 */

// translation.json is a flat key map, but a couple of values are string[]
// (e.g. home.hot_tags), so it needs the two-step cast.
const locale = zh as unknown as Record<string, string>;

describe("static SEO shells", () => {
  it("describes /collections the way the live page describes itself", () => {
    const page = STATIC_SEO_PAGES.collections;

    expect(page.title).toContain(locale["collections.title"]);
    expect(page.desc).toBe(locale["collections.page_desc"]);
    expect(page.noscript).toContain(locale["collections.title"]);
  });

  it("keeps every shell non-empty and brand-suffixed", () => {
    for (const [route, page] of Object.entries(STATIC_SEO_PAGES)) {
      expect(page.title, `${route} title`).toContain("佛津");
      expect(page.desc.length, `${route} desc`).toBeGreaterThan(10);
      expect(page.noscript, `${route} noscript`).toContain("<h1>");
    }
  });
});
