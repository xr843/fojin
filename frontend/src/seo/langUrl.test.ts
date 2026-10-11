import { describe, expect, it } from "vitest";
import { langUrl, ogLocaleFor, seoTitle, toSeoLang } from "./langUrl";

// Must stay byte-identical to backend/app/services/seo_lang.py (see its tests).
describe("langUrl", () => {
  it("builds the three variants", () => {
    expect(langUrl("/texts/1", "zh")).toBe("https://fojin.app/texts/1");
    expect(langUrl("/texts/1", "zh-Hant")).toBe("https://fojin.app/texts/1?lang=zh-Hant");
    expect(langUrl("/", "en")).toBe("https://fojin.app/?lang=en");
  });

  it("normalises UI languages onto the three SEO variants", () => {
    expect(toSeoLang("zh-Hant")).toBe("zh-Hant");
    expect(toSeoLang("en")).toBe("en");
    expect(toSeoLang("en-US")).toBe("en");
    expect(toSeoLang("zh")).toBe("zh");
    expect(toSeoLang("ja")).toBe("zh");
    expect(toSeoLang("")).toBe("zh");
    expect(toSeoLang("EN")).toBe("en");
    expect(toSeoLang("zh-hant")).toBe("zh-Hant");
  });

  it("maps og:locale", () => {
    expect(ogLocaleFor("zh")).toBe("zh_CN");
    expect(ogLocaleFor("zh-Hant")).toBe("zh_TW");
    expect(ogLocaleFor("en")).toBe("en_US");
  });
});

describe("seoTitle", () => {
  it("pairs simplified with the stored traditional form on zh pages, like the server", () => {
    expect(seoTitle("般若波羅蜜多心經", "zh")).toBe("般若波罗蜜多心经（般若波羅蜜多心經）");
    expect(seoTitle("中阿含", "zh")).toBe("中阿含");
  });
  it("keeps the stored form elsewhere", () => {
    expect(seoTitle("般若波羅蜜多心經", "zh-Hant")).toBe("般若波羅蜜多心經");
    expect(seoTitle("般若波羅蜜多心經", "en")).toBe("般若波羅蜜多心經");
  });
});
