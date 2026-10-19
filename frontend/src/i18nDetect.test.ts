import { afterEach, describe, expect, it } from "vitest";
import { UI_LANG_STORAGE_KEY, chineseFromLanguages, dropLegacyUILang, rememberUILang } from "./i18nDetect";

describe("chineseFromLanguages（#1340：中文 Windows + 英文界面浏览器）", () => {
  it("英文排在前、中文排在后，仍给中文", () => {
    // 站长本机 Chrome 实测的语言列表
    expect(chineseFromLanguages(["en-GB", "zh-CN", "zh", "en-US", "en"])).toBe("zh");
  });

  it("台港澳与显式 Hant 给繁体，取列表里第一个中文", () => {
    expect(chineseFromLanguages(["en-US", "zh-TW"])).toBe("zh-Hant");
    expect(chineseFromLanguages(["zh-HK", "zh-CN"])).toBe("zh-Hant");
    expect(chineseFromLanguages(["zh-Hant-TW"])).toBe("zh-Hant");
    expect(chineseFromLanguages(["zh-SG", "zh-TW"])).toBe("zh");
  });

  it("没有中文就交给标准检测，不硬塞中文", () => {
    expect(chineseFromLanguages(["en-US", "de"])).toBeUndefined();
    expect(chineseFromLanguages([])).toBeUndefined();
    expect(chineseFromLanguages(undefined)).toBeUndefined();
    // 前缀相同但不是中文
    expect(chineseFromLanguages(["zha"])).toBeUndefined();
  });
});

describe("界面语言的持久化", () => {
  afterEach(() => localStorage.clear());

  it("主动选择写进新键，旧的被动键被清掉", () => {
    localStorage.setItem("i18nextLng", "en");
    dropLegacyUILang();
    rememberUILang("zh");
    expect(localStorage.getItem(UI_LANG_STORAGE_KEY)).toBe("zh");
    expect(localStorage.getItem("i18nextLng")).toBeNull();
  });
});
