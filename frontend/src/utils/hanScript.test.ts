import { describe, expect, it } from "vitest";
import { localizeHan, scriptForLanguage } from "./hanScript";

/**
 * Backend-supplied text titles (`title_zh`) come straight out of CBETA, which
 * stores traditional Chinese. The UI happily renders them next to hand-curated
 * simplified copy, so a 中文简体 reader sees 大方廣佛華嚴經 sitting directly
 * under 华严经系列. The script a title is rendered in should follow the UI
 * language, not the upstream corpus.
 */

describe("scriptForLanguage", () => {
  it("maps the simplified locales", () => {
    expect(scriptForLanguage("zh")).toBe("simplified");
    expect(scriptForLanguage("zh-CN")).toBe("simplified");
  });

  it("maps the traditional locales", () => {
    expect(scriptForLanguage("zh-Hant")).toBe("traditional");
    expect(scriptForLanguage("zh-TW")).toBe("traditional");
    expect(scriptForLanguage("zh-HK")).toBe("traditional");
  });

  it("renders Chinese titles simplified for non-Chinese UI languages", () => {
    // The curated en.json keeps canonical titles in simplified Chinese, so
    // English readers should see the same script rather than a third variant.
    expect(scriptForLanguage("en")).toBe("simplified");
  });
});

describe("localizeHan", () => {
  it("folds CBETA traditional titles to simplified for zh readers", () => {
    expect(localizeHan("大方廣佛華嚴經", "zh")).toBe("大方广佛华严经");
    expect(localizeHan("瑜伽師地論", "zh")).toBe("瑜伽师地论");
    expect(localizeHan("阿毘達磨俱舍釋論", "zh")).toBe("阿毘达磨俱舍释论");
  });

  it("keeps traditional titles traditional for zh-Hant readers", () => {
    expect(localizeHan("大方廣佛華嚴經", "zh-Hant")).toBe("大方廣佛華嚴經");
  });

  it("converts simplified input to traditional for zh-Hant readers", () => {
    expect(localizeHan("大方广佛华严经", "zh-TW")).toBe("大方廣佛華嚴經");
  });

  it("leaves text with no Han characters untouched", () => {
    expect(localizeHan("T0279", "zh")).toBe("T0279");
    expect(localizeHan("", "zh")).toBe("");
  });

  it("is a no-op when the text is already in the target script", () => {
    expect(localizeHan("瑜伽师地论", "zh")).toBe("瑜伽师地论");
  });
});
