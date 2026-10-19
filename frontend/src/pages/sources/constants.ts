import type { TFunction } from "i18next";

// Raw region values as returned by the API `region` field — kept in Chinese
// because they are data identifiers (filter values, group keys), not display
// strings. Display sites must wrap them: t(`region.${r}`, r).
export const REGION_ORDER = [
  "中国大陆", // i18n-exempt
  "中国台湾", // i18n-exempt
  "中国香港", // i18n-exempt
  "中国澳门", // i18n-exempt
  "日本", // i18n-exempt
  "韩国", // i18n-exempt
  "越南", // i18n-exempt
  "泰国", // i18n-exempt
  "缅甸", // i18n-exempt
  "斯里兰卡", // i18n-exempt
  "印度", // i18n-exempt
  "尼泊尔", // i18n-exempt
  "不丹", // i18n-exempt
  "蒙古", // i18n-exempt
  "老挝", // i18n-exempt
  "柬埔寨", // i18n-exempt
  "美国", // i18n-exempt
  "加拿大", // i18n-exempt
  "英国", // i18n-exempt
  "德国", // i18n-exempt
  "法国", // i18n-exempt
  "荷兰", // i18n-exempt
  "比利时", // i18n-exempt
  "奥地利", // i18n-exempt
  "挪威", // i18n-exempt
  "丹麦", // i18n-exempt
  "意大利", // i18n-exempt
  "西班牙", // i18n-exempt
  "捷克", // i18n-exempt
  "俄罗斯", // i18n-exempt
  "澳大利亚", // i18n-exempt
  "国际", // i18n-exempt
];

export const LANG_ORDER = ["zh", "lzh", "sa", "pi", "bo", "en", "ja", "ko"];

// Research-field codes → zh display names (data values matching the API
// `research_fields` field). Display sites must wrap them:
// t(`field.${code}`, FIELD_NAMES[code]).
export const FIELD_NAMES: Record<string, string> = {
  han: "汉传佛教", // i18n-exempt
  theravada: "南传佛教", // i18n-exempt
  tibetan: "藏传佛教", // i18n-exempt
  dunhuang: "敦煌学", // i18n-exempt
  art: "佛教艺术", // i18n-exempt
  dictionary: "辞典工具", // i18n-exempt
  dh: "数字人文", // i18n-exempt
};

export const FIELD_ORDER = ["han", "theravada", "tibetan", "dictionary", "dh", "dunhuang", "art"];

export function getChannelLabel(channelType: string, t: TFunction): string {
  if (channelType === "git") return "Git";
  if (channelType === "bulk_dump") return t("sources.channel_bulk");
  if (channelType === "api") return "API";
  return channelType;
}

export function trackSourceClick(
  code: string,
  kind: "visit" | "search" | "distribution",
  extra?: Record<string, string | number>,
): void {
  if (typeof window === "undefined" || !window.umami) return;
  window.umami.track("source_click", { code, kind, ...extra });
}

// 「常用数据源」：手机上分组默认收起，首屏一张数据源都看不到；这里把编辑认为最常用的
// 12 个站做成紧凑链接放在页首。⚠️名单**不能**说成「读者点击排行」：2026-10-19 复核
// 发现点击主要由位置决定——默认页最前 12 张卡拿走 38% 点击（人均 32 次），组内第 13
// 位以后的 381 个源人均 0.5 次，所以点击数基本复述了 sort_order。名单 = 编辑精选，
// 参考了点击但不以它为准；每季度复核一次。
export const FEATURED_SOURCE_CODES = [
  "books-fo",
  "cbeta-archive",
  "fanfoyan-dict",
  "cbeta",
  "yuezang",
  "dianjin",
  "shidianguji",
  "xuefo",
  "cbeta-tripitaka",
  "foyan",
  "84000",
  "dunhuang-iiif",
] as const;
