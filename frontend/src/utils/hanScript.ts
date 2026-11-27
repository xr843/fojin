/**
 * Render Han text in the script the UI language asks for.
 *
 * Backend text titles (`title_zh`) are passed through from CBETA, which stores
 * traditional Chinese, while the hand-curated page copy is written per locale.
 * Rendering the upstream string verbatim put 大方廣佛華嚴經 directly under
 * 华严经系列 for 中文简体 readers — the corpus's script leaking into the UI.
 * The script a title renders in should follow the reader's language.
 *
 * Conversion is OpenCC's 1 char → 1 char mapping (same lib the citation matcher
 * already folds with), so offsets are preserved and non-Han text is untouched.
 */
import * as OpenCC from "opencc-js";
import { scriptForLanguage, type HanScript } from "./hanLocale";

const toSimplified = OpenCC.Converter({ from: "tw", to: "cn" });
const toTraditional = OpenCC.Converter({ from: "cn", to: "tw" });

export { scriptForLanguage };
export type { HanScript };

/** Convert `text` into the Han script matching `language`. */
export function localizeHan(text: string, language: string): string {
  if (!text) return text;
  try {
    return scriptForLanguage(language) === "traditional"
      ? toTraditional(text)
      : toSimplified(text);
  } catch {
    // Never let a converter hiccup blank out a title.
    return text;
  }
}

/*
 * 繁转简后「著」的校正。OpenCC tw→cn 把「著」按「着」处理（「執著」→「执着」对），但「著」作「撰著」讲时
 * 也一律转成「着」：作者栏「智旭著」→「智旭着」、经名「楊仁山居士遺著」→「遗着」、辞典「著有《…》」→「着有」。
 * 2026-11-27 生产实测：作者栏 159 条、经名 4 条、辞典摘录约千条中招。
 * 只用在经名 / 作者栏 / 辞典释义这类现代说明文字上——经文原文里「無所著」「著衣」的「着」本来就对，不能套。
 */
const ZHU_AUTHOR_BEFORE = "(杂|遗|新|编|辑|撰|论|名|合|原|另)着"; // i18n-exempt — 文字校正规则
const ZHU_RULES_COMMON: Array<[RegExp, string]> = [
  [/着(?=[《〈])/g, "著"], // i18n-exempt — 文字校正规则； 着《宗镜录》
  [/着(语|述|作)/g, "著$1"], // i18n-exempt — 文字校正规则； 着语（禅宗著语）、着述
  [new RegExp(ZHU_AUTHOR_BEFORE, "g"), "$1著"], // i18n-exempt — 文字校正规则； 杂着、遗着、编着、辑着、论着
  [/无着(?=菩萨|论师|造|所造|、世亲|与世亲)/g, "无著"], // i18n-exempt — 文字校正规则； 无著菩萨（Asaṅga）
];

function applyZhu(s: string, rules: Array<[RegExp, string]>): string {
  return rules.reduce((acc, [re, to]) => acc.replace(re, to), s);
}

/** 经名、作者 / 译者栏（「智旭著」「圓悟著（全角空格）真啟編」「宗杲集並著語」）：转换后校正「著」。 */
export function localizeTitle(text: string, language: string): string {
  const out = localizeHan(text, language);
  if (!out || scriptForLanguage(language) === "traditional" || !out.includes("着")) return out; // i18n-exempt — 文字校正规则
  return applyZhu(out, [
    ...ZHU_RULES_COMMON,
    // 「某某着」在末尾或分隔符前＝撰著；执着 / 染着 / 贪着这类除外
    [/(?<![执染贪爱取味耽])着(?=$|[\s\u3000，,、；;并（(])/g, "著"], // i18n-exempt — 文字校正规则
    [/无着/g, "无著"], // i18n-exempt — 文字校正规则；作者栏 / 经名里的「無著」是人名（无著菩萨、无著道忠、无著妙总）
  ]);
}

/** 辞典释义这类现代白话（里面常夹经文引语）：只改有把握的几种「著」。 */
export function localizeProse(text: string, language: string): string {
  const out = localizeHan(text, language);
  if (!out || scriptForLanguage(language) === "traditional" || !out.includes("着")) return out; // i18n-exempt — 文字校正规则
  return applyZhu(out, [
    ...ZHU_RULES_COMMON,
    [/(^|[。，；：、）\s])着有(?![、，。；者])/g, "$1著有"], // i18n-exempt — 文字校正规则；「著有《…》」：句首 / 标点后（「执着有」不动）
    [/另着有/g, "另著有"], // i18n-exempt — 文字校正规则
    [/）着(?=[。，；])/g, "）著"], // i18n-exempt — 文字校正规则；「寂光（1580～1645）著。」
    [/着(?=[，,][^。]{0,12}?译)/g, "著"], // i18n-exempt — 文字校正规则；「龙树菩萨著，后秦鸠摩罗什译」
    [/(菩萨|大师|禅师|法师|论师|尊者)着(?=[。，；])/g, "$1著"], // i18n-exempt — 文字校正规则
    [/(?<![无不])所着(?=之|有|[。，；])/g, "所著"], // i18n-exempt — 文字校正规则；「空海所著之」，「无所着」不动
  ]);
}

