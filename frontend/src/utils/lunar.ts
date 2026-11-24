/**
 * 北京日期 → 农历（如「十月十六」「冬月初一」「闰五月初三」）。
 *
 * 不用浏览器的 Intl 农历：它在朔日落在北京午夜附近时会错一天（ICU 把 2027、2030 年春节都
 * 算错），见 backend/scripts/build_lunar_months.py。这里查那张由传统农历表生成、并对过
 * 权威万年历的月表；超出表的日期返回 null（不显示农历，不猜）。
 */
import table from "../data/lunarMonths.json";

const MONTHS = ["正月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "冬月", "腊月"]; // i18n-exempt — 农历历法名称（数据，只在中文界面显示）
const DIGITS = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]; // i18n-exempt — 农历历法名称（数据，只在中文界面显示）

function dayName(n: number): string {
  if (n <= 10) return "初" + DIGITS[n]; // i18n-exempt — 农历历法名称（数据，只在中文界面显示）
  if (n < 20) return "十" + DIGITS[n - 10]; // i18n-exempt — 农历历法名称（数据，只在中文界面显示）
  if (n === 20) return "二十"; // i18n-exempt — 农历历法名称（数据，只在中文界面显示）
  if (n < 30) return "廿" + DIGITS[n - 20]; // i18n-exempt — 农历历法名称（数据，只在中文界面显示）
  return "三十"; // i18n-exempt — 农历历法名称（数据，只在中文界面显示）
}

const toDays = (key: string) => {
  const [y, m, d] = key.split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 86_400_000;
};

export const LUNAR_TABLE_UNTIL: string = table.until;

/** dateKey 为北京日期 YYYY-MM-DD；返回简体写法，繁体由调用方用 localizeHan 转（腊→臘）。 */
export function lunarLabel(dateKey: string): string | null {
  if (dateKey >= table.until) return null;
  const months = table.months;
  let i = months.length - 1;
  while (i >= 0 && months[i].start > dateKey) i--;
  if (i < 0) return null;
  const m = months[i];
  const day = toDays(dateKey) - toDays(m.start) + 1;
  if (day < 1 || day > 30) return null;
  return (m.leap ? "闰" : "") + MONTHS[m.month - 1] + dayName(day); // i18n-exempt — 农历历法名称（数据，只在中文界面显示）
}
