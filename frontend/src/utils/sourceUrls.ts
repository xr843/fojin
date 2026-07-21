import type { TFunction } from "i18next";
/**
 * 统一的外部数据源搜索 URL 构建器
 * 所有需要生成外部搜索链接的组件都应使用此文件
 *
 * 搜索 URL 模板存储在 /src/config/searchPatterns.json
 * 使用 {q} 占位符表示查询词
 */

import SEARCH_TEMPLATES from "../config/searchPatterns.json";

/**
 * 为指定数据源和查询词生成搜索 URL
 * @returns 搜索 URL 或 null（无已知模板时）
 */
export function buildSearchUrl(code: string, query: string): string | null {
  const template = (SEARCH_TEMPLATES as Record<string, string>)[code];
  if (!template) return null;
  const q = encodeURIComponent(query);
  return template.replace(/\{q\}/g, q);
}

/**
 * 判断数据源是否有直接搜索 URL（已注册的站内搜索模板）
 */
export function hasDirectSearchUrl(code: string): boolean {
  return code in SEARCH_TEMPLATES;
}

/** 已验证搜索 URL 的数据源数量 */
export const SEARCHABLE_SOURCE_COUNT = Object.keys(SEARCH_TEMPLATES).length;

/**
 * 为 CBETA 编号生成 CBETA Online 阅读链接
 */
export function buildCbetaReadUrl(cbetaId: string): string | null {
  if (/^[TX]\d+[a-z]?$/i.test(cbetaId)) {
    return `https://cbetaonline.dila.edu.tw/zh/${cbetaId}`;
  }
  return null;
}

/**
 * 站内阅读器的 URL。路由是 /texts/:id/read，卷号走 ?juan= 查询参数
 * （TextReaderPage 读 searchParams.get("juan")）。
 *
 * 所有指向站内阅读器的链接都应经过这里：曾经有卡片手写 `/read/:id/:juan`，
 * 那条路由从不存在，点进去一律 404。
 */
export function buildReaderUrl(textId: number, juanNum?: number | null): string {
  const base = `/texts/${textId}/read`;
  return juanNum == null ? base : `${base}?juan=${juanNum}`;
}

const SOURCE_LABEL_KEYS: Record<string, string> = {
  cbeta: "sourceLabel.cbeta",
  "cbeta-org": "sourceLabel.cbeta",
  suttacentral: "sourceLabel.suttacentral",
  "suttacentral-org": "sourceLabel.suttacentral",
  gretil: "sourceLabel.gretil",
  "84000": "sourceLabel.84000",
  bdrc: "sourceLabel.bdrc",
  "tbrc-bdrc": "sourceLabel.bdrc",
  ctext: "sourceLabel.ctext",
  sat: "sourceLabel.sat",
  "sat-utokyo": "sourceLabel.sat",
  shidianguji: "sourceLabel.shidianguji",
  dianjin: "sourceLabel.dianjin",
  "kanseki-repo": "sourceLabel.kanseki",
  "lotsawa-house": "sourceLabel.lotsawaHouse",
  buddhanexus: "sourceLabel.buddhanexus",
  dharmanexus: "sourceLabel.dharmanexus",
  accesstoinsight: "sourceLabel.accessToInsight",
  dhammatalks: "sourceLabel.dhammatalks",
  dharmacloud: "sourceLabel.dharmaCloud",
  ddb: "sourceLabel.ddb",
};

/**
 * 获取数据源的显示名称。Pass t from useTranslation for locale-aware UI.
 */
export function getSourceLabel(code: string, t?: TFunction): string {
  const key = SOURCE_LABEL_KEYS[code];
  return key && t ? t(key, { defaultValue: code.toUpperCase() }) : code.toUpperCase();
}

/** 阅读 URL 模板（非搜索，而是具体文本阅读） */
const READ_URL_PATTERNS: Record<string, (id: string) => string> = {
  cbeta: (id) => `https://cbetaonline.dila.edu.tw/zh/${id}`,
  "cbeta-org": (id) => `https://cbetaonline.dila.edu.tw/zh/${id}`,
  suttacentral: (id) => `https://suttacentral.net/${id}`,
  "suttacentral-org": (id) => `https://suttacentral.net/${id}`,
  "84000": (id) => `https://read.84000.co/translation/${id}.html`,
  ctext: (id) => `https://ctext.org/${id}`,
  sat: (id) => `https://21dzk.l.u-tokyo.ac.jp/SAT2018/master30.php?no=${id}`,
  "sat-utokyo": (id) => `https://21dzk.l.u-tokyo.ac.jp/SAT2018/master30.php?no=${id}`,
  accesstoinsight: (id) => `https://www.accesstoinsight.org/tipitaka/${id}`,
  "kanseki-repo": (id) => `https://www.kanripo.org/text/${id}`,
};

/**
 * 为指定数据源和标识符生成阅读 URL
 * @returns 阅读 URL 或 null（无已知模板时）
 */
export function buildSourceReadUrl(sourceCode: string, identifier: string): string | null {
  const fn = READ_URL_PATTERNS[sourceCode];
  return fn ? fn(identifier) : null;
}

/** 语言代码 → 中文名称映射 */
export const LANG_NAMES: Record<string, string> = {
  lzh: "古典汉文", // i18n-exempt
  sa: "梵文", // i18n-exempt
  pi: "巴利文", // i18n-exempt
  bo: "藏文", // i18n-exempt
  pgd: "犍陀罗语", // i18n-exempt
  kho: "和阗语", // i18n-exempt
  sog: "粟特语", // i18n-exempt
  xto: "吐火罗语", // i18n-exempt
  txb: "吐火罗语", // i18n-exempt
  oui: "古维吾尔语", // i18n-exempt
  txg: "西夏文", // i18n-exempt
  cmg: "蒙文", // i18n-exempt
  mnc: "满文", // i18n-exempt
  th: "泰文", // i18n-exempt
  my: "缅文", // i18n-exempt
  si: "僧伽罗文", // i18n-exempt
  km: "高棉文", // i18n-exempt
  ja: "日文", // i18n-exempt
  ko: "韩文", // i18n-exempt
  vi: "越南文", // i18n-exempt
  en: "英文", // i18n-exempt
  de: "德文", // i18n-exempt
  fr: "法文", // i18n-exempt
  lo: "老挝文", // i18n-exempt
  zh: "中文", // i18n-exempt
  ru: "俄文", // i18n-exempt
  nl: "荷兰文", // i18n-exempt
  pt: "葡萄牙文", // i18n-exempt
  ne: "尼泊尔文", // i18n-exempt
  hi: "印地文", // i18n-exempt
  jv: "爪哇文", // i18n-exempt
  es: "西班牙文", // i18n-exempt
  mn: "蒙古文", // i18n-exempt
  bn: "孟加拉文", // i18n-exempt
  cs: "捷克文", // i18n-exempt
  mul: "多语种", // i18n-exempt
};

export function getLangName(code: string): string {
  return LANG_NAMES[code] || code;
}

/**
 * Locale-aware language name for display. getLangName returns the Chinese
 * data name (used as grouping/dedup keys); this resolves through lang.*
 * translation keys with the Chinese name as fallback. Pass t from
 * useTranslation so language switches re-render callers.
 */
export function localizedLangName(code: string, t: TFunction): string {
  return t(`lang.${code}`, { defaultValue: LANG_NAMES[code] || code });
}

/** 中文名称 → ISO 代码反向映射（处理数据库中未规范化的语言名） */
const NAME_TO_CODE: Record<string, string> = Object.fromEntries(
  Object.entries(LANG_NAMES).map(([k, v]) => [v, k]),
);
// 额外别名
NAME_TO_CODE["日语"] = "ja"; // i18n-exempt
NAME_TO_CODE["韩语"] = "ko"; // i18n-exempt
NAME_TO_CODE["英语"] = "en"; // i18n-exempt
NAME_TO_CODE["德语"] = "de"; // i18n-exempt
NAME_TO_CODE["法语"] = "fr"; // i18n-exempt
NAME_TO_CODE["荷兰语"] = "nl"; // i18n-exempt
NAME_TO_CODE["西班牙语"] = "es"; // i18n-exempt
NAME_TO_CODE["繁体中文"] = "zh"; // i18n-exempt

/** 将可能的中文语言名规范化为 ISO 代码 */
export function normalizeLangCode(raw: string): string {
  return NAME_TO_CODE[raw] || raw;
}
