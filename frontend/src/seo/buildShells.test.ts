import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { localizeShell, shellPlan, toTraditional } from "./buildShells";

// The real index.html — the template the build stamps every shell from.
const template = readFileSync(resolve(__dirname, "../../index.html"), "utf-8");
const meta = { title: "佛经 AI 问答 | 佛津 FoJin", desc: "向大藏经提问", noscript: "<h1>佛津</h1>" };

describe("localizeShell", () => {
  it("emits a self-canonical zh-Hant variant with hreflang", () => {
    const html = localizeShell(template, {
      lang: "zh-Hant",
      path: "/chat",
      meta: { ...meta, title: toTraditional(meta.title) },
      hreflang: true,
    });
    expect(html).toContain('<html lang="zh-Hant">');
    expect(html).toContain('<link rel="canonical" href="https://fojin.app/chat?lang=zh-Hant"');
    expect(html).toContain('<meta property="og:url" content="https://fojin.app/chat?lang=zh-Hant"');
    expect(html).toContain('<meta property="og:locale" content="zh_TW"');
    expect(html).toContain('"inLanguage": "zh-Hant"');
    expect(html).toContain("<title>佛經 AI 問答 | 佛津 FoJin</title>");
    expect(html.match(/rel="alternate" hreflang=/g)).toHaveLength(4);
    expect(html).toContain('<link rel="alternate" hreflang="x-default" href="https://fojin.app/chat" />');
  });

  it("keeps the zh variant on the bare URL", () => {
    const html = localizeShell(template, { lang: "zh", path: "/chat", meta, hreflang: true });
    expect(html).toContain('<html lang="zh-Hans">');
    expect(html).toContain('<link rel="canonical" href="https://fojin.app/chat"');
    expect(html).toContain('"inLanguage": "zh-Hans"');
  });

  it("leaves the SPA fallback without hreflang", () => {
    const html = localizeShell(template, { lang: "en", path: "/", meta, hreflang: false });
    expect(html).toContain('<html lang="en">');
    expect(html).not.toContain("hreflang=");
  });

  it("drops Chinese leftovers from English share-card tags", () => {
    const html = localizeShell(template, { lang: "en", path: "/", meta: { ...meta, title: "FoJin — Ask the canon" }, hreflang: false });
    expect(html).toContain('<meta property="og:site_name" content="FoJin"');
    expect(html).toContain('<meta property="og:image:alt" content="FoJin — Ask the canon"');
  });

  it("escapes attribute values", () => {
    const html = localizeShell(template, { lang: "en", path: "/x", meta: { ...meta, desc: 'a "b" <c>' }, hreflang: false });
    expect(html).toContain('<meta name="description" content="a &quot;b&quot; &lt;c&gt;"');
  });
});

describe("shellPlan", () => {
  const plan = shellPlan();
  const byFile = new Map(plan.map((p) => [p.outFile, p]));

  it("covers every prebuilt route in three languages", () => {
    const routes = [
      "_home/index",
      "chat/index",
      "search/index",
      "sources/index",
      "kg/index",
      "collections/index",
      "dictionary/index",
      "cross-canon/index",
      "sutras/heart-sutra/index",
      "sutras/vimalakirti-sutra/index",
      "collections/huayan/index",
      "collections/pali-canon/index",
    ];
    for (const route of routes) {
      for (const sfx of ["", ".zh-Hant", ".en"]) {
        expect(byFile.has(`${route}${sfx}.html`), `${route}${sfx}`).toBe(true);
      }
    }
  });

  it("emits no /topics shell (merged into /collections; nginx 301s it)", () => {
    // A dist/topics/ directory would resurrect a second 「经典专题」 page for
    // anything that bypasses the nginx 301 (and re-arm the try_files $uri/ trap).
    expect(plan.some((p) => p.outFile.startsWith("topics/"))).toBe(false);
  });

  it("builds language-only SPA fallbacks without hreflang", () => {
    expect(byFile.get("index.zh-Hant.html")?.hreflang).toBe(false);
    expect(byFile.get("index.en.html")?.hreflang).toBe(false);
    expect(byFile.has("index.html")).toBe(false); // the template itself is left untouched
  });

  it("gives /search no hreflang (robots-blocked results page)", () => {
    expect(byFile.get("search/index.en.html")?.hreflang).toBe(false);
    expect(byFile.get("chat/index.en.html")?.hreflang).toBe(true);
  });

  it("uses each language's own copy", () => {
    expect(byFile.get("collections/huayan/index.en.html")?.meta.title).toContain("Avatamsaka");
    expect(byFile.get("collections/huayan/index.zh-Hant.html")?.meta.title).toContain("華嚴經系列");
    expect(byFile.get("sutras/heart-sutra/index.en.html")?.meta.title).toContain("Heart Sutra");
    expect(byFile.get("sutras/heart-sutra/index.zh-Hant.html")?.meta.title).toContain("心經");
    expect(byFile.get("chat/index.en.html")?.meta.title).not.toMatch(/[一-鿿]{3}/);
    expect(byFile.get("_home/index.en.html")?.meta.title).toContain("FoJin");
  });

  it("points every shell at its own path", () => {
    expect(byFile.get("_home/index.en.html")?.path).toBe("/");
    expect(byFile.get("collections/huayan/index.html")?.path).toBe("/collections/huayan");
    expect(byFile.get("cross-canon/index.zh-Hant.html")?.path).toBe("/cross-canon");
  });
});
