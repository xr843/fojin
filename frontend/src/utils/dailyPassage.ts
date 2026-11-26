/**
 * 每日一段：同一天（北京时间）所有人看到同一段，按日期轮换。
 *
 * 段落池在 src/data/dailyPassages.json，由 backend/scripts/build_daily_passages.py 生成：
 * 每一段都经全藏逐字核对（/api/verify/claim 相似度 1.0），带回经名、卷、阅读器行号链接——
 * 不靠人记忆写出处，核不到的不收。
 */
import passages from "../data/dailyPassages.json";
import festivals from "../data/dailyFestivals.json";
import { scriptForLanguage } from "./hanLocale";
import { lunarParts } from "./lunar";

export interface DailyPassage {
  text: string;
  title_zh: string;
  cbeta_id: string;
  text_id: number;
  juan_num: number;
  /** 站内路径，直达阅读器那一行并高亮，如 /texts/7/read?juan=1&anchor=p0749c22&hl=… */
  reader_path: string;
  /** 简体版（scripts/daily-hans.mjs 用 OpenCC 预先算好）：首页不能引 OpenCC，靠它显示简体 */
  text_hans?: string;
  title_hans?: string;
}

export const DAILY_PASSAGES = passages as DailyPassage[];

/**
 * 佛教节日（汉传通行农历日期）当天换成与这位佛菩萨相关的经句，同样全藏逐字核对过，
 * 由 build_daily_passages.py --festivals 生成。节日名是数据（简体 name / 繁体 name_hant）。
 */
export interface DailyFestival extends DailyPassage {
  /** 农历「月-日」，如 "02-19"；"07-30" 遇小月在廿九 */
  key: string;
  name: string;
  name_hant?: string;
}

export const DAILY_FESTIVALS = festivals as DailyFestival[];

/** 这一天（北京日期）是不是佛教节日；闰月不算（节日按本月过）。 */
export function festivalFor(dateKey: string, pool: DailyFestival[] = DAILY_FESTIVALS): DailyFestival | null {
  const p = lunarParts(dateKey);
  if (!p || p.leap) return null;
  const mm = String(p.month).padStart(2, "0");
  const keys = [`${mm}-${String(p.day).padStart(2, "0")}`];
  if (p.day === 29 && p.monthDays === 29) keys.push(`${mm}-30`);
  return pool.find((f) => keys.includes(f.key)) ?? null;
}

/** 节日名按界面繁简取；非中文界面不显示（农历也只给中文界面）。 */
export function festivalName(f: DailyFestival | null, lang: string): string | null {
  if (!f || !lang.startsWith("zh")) return null;
  return scriptForLanguage(lang) === "traditional" ? (f.name_hant ?? f.name) : f.name;
}

/** 北京时间的日期键 YYYY-MM-DD：零点在北京切换，海外读者也看同一段。 */
export function beijingDateKey(now: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

const EPOCH = Date.UTC(2026, 0, 1);

/** 第几段：从 2026-01-01 起按天数取模。池子顺序已在生成时打散，相邻两天不会落在同一部经。 */
export function dailyIndex(dateKey: string, n: number): number {
  const [y, m, d] = dateKey.split("-").map(Number);
  const days = Math.floor((Date.UTC(y, m - 1, d) - EPOCH) / 86_400_000);
  return ((days % n) + n) % n;
}

export function pickDaily(
  now: Date,
  pool: DailyPassage[] = DAILY_PASSAGES,
): { passage: DailyPassage; dateKey: string; festival: DailyFestival | null } {
  const dateKey = beijingDateKey(now);
  // 节日当天用节日经句；轮换序号照常按天数走，节日过后接着原来的顺序
  const festival = festivalFor(dateKey);
  return { passage: festival ?? pool[dailyIndex(dateKey, pool.length)], dateKey, festival };
}

/**
 * 给经句加引号：繁体界面用「」，简体与其他界面用“”（大陆通行）。
 * 池里存的是不带引号、带句末标点的原句；引号只在展示与分享时加。
 * 不引 hanScript（它会把 OpenCC 拖进首页的静态导入链）。
 */
export function quotePassage(text: string, lang: string): string {
  return scriptForLanguage(lang) === "traditional" ? `「${text}」` : `“${text}”`;
}

/**
 * 经句字体：简体界面用毛笔体（马善政），标点落到文楷；繁体界面整句文楷（马善政没有繁体字形）。
 * 页面 CSS 与分享图 canvas 共用这一串。
 */
export function passageFontFamily(lang: string): string {
  return scriptForLanguage(lang) === "traditional"
    ? '"FoJin Daily Kai", "Noto Serif SC", serif'
    : '"FoJin Daily Brush", "FoJin Daily Kai", "Noto Serif SC", serif';
}

/** 一行放得下就单行显示（桌面）；超过这个字数（含引号标点）按分句换行。 */
export const ONE_LINE_MAX_CHARS = 36;

/**
 * 把经句切成分句（每段带着自己的标点与引号），页面上每段 inline-block，只在标点处换行——
 * 否则窄一点的屏幕会把「不能見如來。」」拆成「不能見如」+「來。」」，孤字落到第二行。
 */
export function splitClauses(text: string): string[] {
  return text.match(/[「“]?[^，。；：？！、]+[，。；：？！、]*[」”]?/g) ?? [text];
}

/**
 * 首页用的经句与经名：按界面语言选繁/简，不经过 OpenCC（hanScript 会把 550KB 拖进首屏）。
 * 池里原文是繁体；简体取预先算好的 text_hans/title_hans，缺了就退回原文。
 */
export function passageInScript(p: DailyPassage, lang: string): { text: string; title: string } {
  if (scriptForLanguage(lang) === "traditional") return { text: p.text, title: p.title_zh };
  return { text: p.text_hans ?? p.text, title: p.title_hans ?? p.title_zh };
}
