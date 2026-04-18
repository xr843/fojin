export const REGION_ORDER = [
  "中国大陆",
  "中国台湾",
  "中国香港",
  "中国澳门",
  "日本",
  "韩国",
  "越南",
  "泰国",
  "缅甸",
  "斯里兰卡",
  "印度",
  "尼泊尔",
  "不丹",
  "蒙古",
  "老挝",
  "柬埔寨",
  "美国",
  "加拿大",
  "英国",
  "德国",
  "法国",
  "荷兰",
  "比利时",
  "奥地利",
  "挪威",
  "丹麦",
  "意大利",
  "西班牙",
  "捷克",
  "俄罗斯",
  "澳大利亚",
  "国际",
];

export const LANG_ORDER = ["zh", "lzh", "sa", "pi", "bo", "en", "ja", "ko"];

export const FIELD_NAMES: Record<string, string> = {
  han: "汉传佛教",
  theravada: "南传佛教",
  tibetan: "藏传佛教",
  dunhuang: "敦煌学",
  art: "佛教艺术",
  dictionary: "辞典工具",
  dh: "数字人文",
};

export const FIELD_ORDER = ["han", "theravada", "tibetan", "dictionary", "dh", "dunhuang", "art"];

export function getChannelLabel(channelType: string): string {
  if (channelType === "git") return "Git";
  if (channelType === "bulk_dump") return "批量";
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
