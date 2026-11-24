/**
 * 每日一段：同一天（北京时间）所有人看到同一段，按日期轮换。
 *
 * 段落池在 src/data/dailyPassages.json，由 backend/scripts/build_daily_passages.py 生成：
 * 每一段都经全藏逐字核对（/api/verify/claim 相似度 1.0），带回经名、卷、阅读器行号链接——
 * 不靠人记忆写出处，核不到的不收。
 */
import passages from "../data/dailyPassages.json";

export interface DailyPassage {
  text: string;
  title_zh: string;
  cbeta_id: string;
  text_id: number;
  juan_num: number;
  /** 站内路径，直达阅读器那一行并高亮，如 /texts/7/read?juan=1&anchor=p0749c22&hl=… */
  reader_path: string;
}

export const DAILY_PASSAGES = passages as DailyPassage[];

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

export function pickDaily(now: Date, pool: DailyPassage[] = DAILY_PASSAGES): { passage: DailyPassage; dateKey: string } {
  const dateKey = beijingDateKey(now);
  return { passage: pool[dailyIndex(dateKey, pool.length)], dateKey };
}
