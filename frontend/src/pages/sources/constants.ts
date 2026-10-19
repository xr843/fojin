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

// 「常用数据源」：读者把 /sources 当导航用——36% 的访问直接从这页进站、26% 点外链
// 出站，而点击高度集中：205 个被点过的源里，前 10 个拿走 46%（Umami 2026-07-20 ~
// 10-18，剔除爬虫与站长）。这些站原本埋在按地区分的 35 个组里，手机上分组默认收起，
// 首屏一张卡都看不到。名单按那 13 周的实际点击排序、人工固定（不做实时排行，免得
// 热门自我强化）；每季度按新数据复核一次。
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
