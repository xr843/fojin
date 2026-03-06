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
 * 为指定数据源和查询词生成搜索 URL，如果没有已知模板则回退到 Google site: 搜索
 */
export function buildSearchUrlWithFallback(code: string, baseUrl: string | null, query: string): string | null {
  const url = buildSearchUrl(code, query);
  if (url) return url;
  if (baseUrl) {
    const domain = baseUrl.replace(/https?:\/\//, "").replace(/\/.*/, "");
    const q = encodeURIComponent(query);
    return `https://www.google.com/search?q=site:${domain}+${q}`;
  }
  return null;
}

/**
 * 判断数据源是否有直接搜索 URL（非 Google 回退）
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

/** 数据源 code → 中文显示名称 */
const SOURCE_LABELS: Record<string, string> = {
  cbeta: "CBETA",
  "cbeta-org": "CBETA",
  suttacentral: "SuttaCentral",
  "suttacentral-org": "SuttaCentral",
  gretil: "GRETIL",
  "84000": "84000",
  bdrc: "BDRC",
  "tbrc-bdrc": "BDRC",
  ctext: "中國哲學書電子化計劃",
  sat: "SAT 大正藏",
  "sat-utokyo": "SAT 大正藏",
  shidianguji: "识典古籍",
  dianjin: "典津",
  "kanseki-repo": "漢籍リポジトリ",
  "lotsawa-house": "Lotsawa House",
  buddhanexus: "Dharmamitra (原BuddhaNexus)",
  dharmanexus: "DharmaNexus",
  accesstoinsight: "Access to Insight",
  dhammatalks: "Dhammatalks",
  dharmacloud: "Dharma Cloud",
  ddb: "DDB 電子佛教辭典",
};

/**
 * 获取数据源的中文显示名称
 */
export function getSourceLabel(code: string): string {
  return SOURCE_LABELS[code] || code.toUpperCase();
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
  lzh: "古典汉文",
  sa: "梵文",
  pi: "巴利文",
  bo: "藏文",
  pgd: "犍陀罗语",
  kho: "和阗语",
  sog: "粟特语",
  xto: "吐火罗语A",
  txb: "吐火罗语B",
  oui: "古维吾尔语",
  txg: "西夏文",
  cmg: "蒙文",
  mnc: "满文",
  th: "泰文",
  my: "缅文",
  si: "僧伽罗文",
  km: "高棉文",
  ja: "日文",
  ko: "韩文",
  vi: "越南文",
  en: "英文",
  de: "德文",
  fr: "法文",
  lo: "老挝文",
  zh: "中文",
  ru: "俄文",
  nl: "荷兰文",
  pt: "葡萄牙文",
  ne: "尼泊尔文",
  hi: "印地文",
  jv: "爪哇文",
};

export function getLangName(code: string): string {
  return LANG_NAMES[code] || code;
}
