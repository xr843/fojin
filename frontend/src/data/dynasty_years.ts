export interface DynastyPeriod {
  key: string;
  name_zh: string;
  name_en: string;
  start: number;
  end: number;
  color: string;
}

export const DYNASTIES: DynastyPeriod[] = [
  { key: "pre_qin", name_zh: "先秦", name_en: "Pre-Qin", start: -770, end: -221, color: "#8b7355" },
  { key: "qin", name_zh: "秦", name_en: "Qin Dynasty", start: -221, end: -206, color: "#4a4a4a" },
  { key: "western_han", name_zh: "西汉", name_en: "Western Han", start: -206, end: 8, color: "#c75450" },
  { key: "eastern_han", name_zh: "東漢", name_en: "Eastern Han", start: 25, end: 220, color: "#d4756b" },
  { key: "three_kingdoms", name_zh: "三國", name_en: "Three Kingdoms", start: 220, end: 280, color: "#6b8e5b" },
  { key: "western_jin", name_zh: "西晉", name_en: "Western Jin", start: 265, end: 316, color: "#7a9e6a" },
  { key: "eastern_jin", name_zh: "東晉", name_en: "Eastern Jin", start: 317, end: 420, color: "#8aae7a" },
  { key: "sixteen_kingdoms", name_zh: "十六國", name_en: "Sixteen Kingdoms", start: 304, end: 439, color: "#9b8b6e" },
  { key: "southern_dynasties", name_zh: "南朝", name_en: "Southern Dynasties", start: 420, end: 589, color: "#b08d57" },
  { key: "northern_dynasties", name_zh: "北朝", name_en: "Northern Dynasties", start: 386, end: 581, color: "#a07d47" },
  { key: "sui", name_zh: "隋", name_en: "Sui Dynasty", start: 581, end: 618, color: "#4a7c9b" },
  { key: "tang", name_zh: "唐", name_en: "Tang Dynasty", start: 618, end: 907, color: "#c75450" },
  { key: "five_dynasties", name_zh: "五代", name_en: "Five Dynasties", start: 907, end: 960, color: "#8b6e5b" },
  { key: "northern_song", name_zh: "北宋", name_en: "Northern Song", start: 960, end: 1127, color: "#4a7c9b" },
  { key: "southern_song", name_zh: "南宋", name_en: "Southern Song", start: 1127, end: 1279, color: "#5a8cab" },
  { key: "liao", name_zh: "遼", name_en: "Liao Dynasty", start: 916, end: 1125, color: "#7a6e5b" },
  { key: "jin_jurchen", name_zh: "金", name_en: "Jin (Jurchen)", start: 1115, end: 1234, color: "#b08d57" },
  { key: "yuan", name_zh: "元", name_en: "Yuan Dynasty", start: 1271, end: 1368, color: "#4a6a4a" },
  { key: "ming", name_zh: "明", name_en: "Ming Dynasty", start: 1368, end: 1644, color: "#8b2500" },
  { key: "qing", name_zh: "清", name_en: "Qing Dynasty", start: 1644, end: 1912, color: "#b08d57" },
  { key: "modern", name_zh: "近現代", name_en: "Modern", start: 1912, end: 2000, color: "#4a4a4a" },
  { key: "india", name_zh: "印度", name_en: "India", start: -500, end: 1200, color: "#d4a56a" },
  { key: "japan", name_zh: "日本", name_en: "Japan", start: 600, end: 1900, color: "#c75480" },
  { key: "korea", name_zh: "高麗/朝鮮", name_en: "Korea", start: 918, end: 1910, color: "#5470c6" },
  { key: "tibet", name_zh: "西藏", name_en: "Tibet", start: 600, end: 1900, color: "#91cc75" },
];

const ALIASES: Record<string, string> = {
  "後漢": "東漢", "劉宋": "南朝", "蕭齊": "南朝", "蕭梁": "南朝",
  "曹魏": "三國", "吳": "三國", "東吳": "三國",
  "北涼": "十六國", "後秦": "十六國", "姚秦": "十六國", "前秦": "十六國", "西秦": "十六國",
  "北魏": "北朝", "東魏": "北朝", "西魏": "北朝", "北齊": "北朝", "北周": "北朝",
  "宋": "北宋", "南齊": "南朝", "梁": "南朝", "陳": "南朝",
};

const BY_NAME = new Map(DYNASTIES.map((d) => [d.name_zh, d]));

export function resolveDynasty(nameZh: string | null | undefined): DynastyPeriod | undefined {
  if (!nameZh) return undefined;
  const canonical = ALIASES[nameZh] ?? nameZh;
  return BY_NAME.get(canonical);
}
