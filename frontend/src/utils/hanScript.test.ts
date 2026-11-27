import { describe, expect, it } from "vitest";
import { localizeHan, localizeProse, localizeTitle, scriptForLanguage } from "./hanScript";

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


describe("繁转简后「著」的校正（2026-11-27 生产实测作者栏 159 条、经名 4 条、辞典摘录约千条转错）", () => {
  it("作者栏 / 经名：撰著的「著」改回，执着义不动", () => {
    expect(localizeTitle("智旭著", "zh")).toBe("智旭著");
    expect(localizeTitle("圓悟著　真啟編", "zh")).toBe("圆悟著　真启编");
    expect(localizeTitle("宗杲集並著語", "zh")).toBe("宗杲集并著语");
    expect(localizeTitle("道忞著（中央圖書館善本書目編在集部別集類）", "zh")).toBe("道忞著（中央图书馆善本书目编在集部别集类）");
    expect(localizeTitle("無著菩薩造  唐 義淨", "zh")).toBe("无著菩萨造  唐 义净");
    expect(localizeTitle("楊仁山居士遺著", "zh")).toBe("杨仁山居士遗著");
    expect(localizeTitle("錦屏破石卓禪師雜著", "zh")).toBe("锦屏破石卓禅师杂著");
    expect(localizeTitle("金剛般若波羅蜜經破取著不壞假名論", "zh")).toBe("金刚般若波罗蜜经破取着不坏假名论");
    expect(localizeTitle("智旭著", "zh-Hant")).toBe("智旭著");
  });

  it("辞典释义：只改有把握的写法；执着、着衣、无所着、「着有、」不动", () => {
    expect(localizeProse("明僧寂光（1580～1645）著。全名", "zh")).toBe("明僧寂光（1580～1645）著。全名");
    expect(localizeProse("印度龍樹菩薩著，後秦鳩摩羅什譯", "zh")).toBe("印度龙树菩萨著，后秦鸠摩罗什译");
    expect(localizeProse("壽六十二。所著有觀經疏", "zh")).toBe("寿六十二。所著有观经疏");
    expect(localizeProse("即空海所著之般若心經祕鍵", "zh")).toBe("即空海所著之般若心经秘键");
    expect(localizeProse("碧巖第二十八則著語曰", "zh")).toBe("碧岩第二十八则著语曰");
    expect(localizeProse("凡夫執著，貪著五欲，上著衣", "zh")).toBe("凡夫执着，贪着五欲，上着衣");
    expect(localizeProse("佛不著塵染，故稱無所著。", "zh")).toBe("佛不着尘染，故称无所着。");
    expect(localizeProse("放逸性；著有、著資財", "zh")).toBe("放逸性；着有、着资财");
    expect(localizeProse("前自著內衣", "zh")).toBe("前自着内衣");
  });
});
