import { describe, expect, it } from "vitest";
import { searchWithLang } from "./syncLangParam";

describe("searchWithLang", () => {
  it("adds lang for non-default languages and keeps other params", () => {
    expect(searchWithLang("?q=%E5%BF%83%E7%BB%8F", "zh-Hant")).toBe("?q=%E5%BF%83%E7%BB%8F&lang=zh-Hant");
  });
  it("replaces an existing lang value", () => {
    expect(searchWithLang("?lang=zh-Hant", "en")).toBe("?lang=en");
  });
  it("removes lang when switching back to zh", () => {
    expect(searchWithLang("?lang=en", "zh")).toBe("");
    expect(searchWithLang("?page=2&lang=en", "zh")).toBe("?page=2");
  });
  it("handles an empty search", () => {
    expect(searchWithLang("", "en")).toBe("?lang=en");
  });
});
