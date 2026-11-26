/**
 * 佛教史长卷（/history）的朝代年表。
 *
 * 名称用繁体，和 DILA 人名规范库的「朝代」字段同一写法（页面显示时再按界面语言转简）。
 * 年份取通行说法（公元纪年，始年含、末年为改朝之年）；并立政权放第二行。
 * `BANDS` 画在长卷顶部；`SPANS` 还包括只用来给「生卒不详」的人定位的短命政权（後秦、北涼……）。
 */

export interface DynastyBand {
  name: string;
  from: number;
  to: number;
  /** 0 = 主线（汉—晋—南朝—隋唐—宋元明清）；1 = 并立（十六国、北朝、辽金） */
  row: 0 | 1;
}

export const BANDS: DynastyBand[] = [
  { name: "東漢", from: 25, to: 220, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "三國", from: 220, to: 266, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "西晉", from: 266, to: 316, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "東晉", from: 317, to: 420, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "劉宋", from: 420, to: 479, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "南齊", from: 479, to: 502, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "南梁", from: 502, to: 557, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "陳", from: 557, to: 589, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "隋", from: 589, to: 618, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "唐", from: 618, to: 907, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "五代十國", from: 907, to: 960, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "北宋", from: 960, to: 1127, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "南宋", from: 1127, to: 1279, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "元", from: 1279, to: 1368, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "明", from: 1368, to: 1644, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "清", from: 1644, to: 1912, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "民國", from: 1912, to: 1949, row: 0 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "十六國", from: 304, to: 439, row: 1 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "北魏", from: 439, to: 534, row: 1 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "東魏", from: 534, to: 550, row: 1 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "北齊", from: 550, to: 577, row: 1 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "北周", from: 577, to: 581, row: 1 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "隋", from: 581, to: 589, row: 1 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "遼", from: 916, to: 1125, row: 1 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  { name: "金", from: 1125, to: 1234, row: 1 }, // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
];

/** 用来给只有朝代、没有生卒的人定位；含 BANDS 之外的政权（按 DILA 的写法）。 */
export const SPANS: Record<string, [number, number]> = {
  ...Object.fromEntries(BANDS.filter((b) => b.row === 0).map((b) => [b.name, [b.from, b.to] as [number, number]])),
  ...Object.fromEntries(BANDS.filter((b) => b.row === 1 && b.name !== "隋").map((b) => [b.name, [b.from, b.to] as [number, number]])), // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  隋: [581, 618], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  北魏: [386, 534], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  曹魏: [220, 266], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  蜀漢: [221, 263], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  孫吳: [222, 280], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  前秦: [351, 394], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  後秦: [384, 417], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  西秦: [385, 431], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  北涼: [397, 439], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  南北朝: [420, 589], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  西魏: [535, 557], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  宋: [960, 1279], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  元: [1271, 1368], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
  晉: [266, 420], // i18n-exempt — DILA 朝代字段原文，显示时经 localizeHan
};

export const TIMELINE_START = 0;
export const TIMELINE_END = 1960;

/** DILA 的朝代字段常是「東晉 後秦」「明 清」：取第一个认得的。 */
export function dynastySpan(dynasty: string | undefined | null): [number, number] | null {
  for (const part of (dynasty ?? "").split(/\s+/)) {
    if (SPANS[part]) return SPANS[part];
  }
  return null;
}

/** 某一年落在主线（第一行）哪个朝代。 */
export function dynastyAt(year: number): DynastyBand | null {
  return BANDS.find((b) => b.row === 0 && year >= b.from && year < b.to) ?? null;
}
