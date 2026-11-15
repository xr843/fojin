/**
 * 阅读续读历史 — localStorage 实现。
 *
 * 对所有访客生效（含未登录）：记录最近阅读的 (text, 卷, 滚动位置)，
 * 供阅读器恢复位置、详情页"继续阅读"、首页"最近阅读"入口使用。
 * 设备本地存储；跨设备同步留给将来的服务端版本（登录权益）。
 */

export interface ReadingEntry {
  textId: number;
  title: string;
  juan: number;
  /** 0..1 — 阅读视口锚点在正文渲染高度中的比例 */
  ratio: number;
  ts: number;
}

const STORAGE_KEY = "fojin-reading-history";
const MAX_ENTRIES = 10;

function readAll(): ReadingEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (e): e is ReadingEntry =>
        e &&
        typeof e.textId === "number" &&
        typeof e.title === "string" &&
        typeof e.juan === "number" &&
        typeof e.ratio === "number" &&
        typeof e.ts === "number",
    );
  } catch {
    // localStorage 不可用（隐私模式）或损坏数据 — 静默降级为"无历史"
    return [];
  }
}

function writeAll(entries: ReadingEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    /* quota / 隐私模式 — 丢弃即可 */
  }
}

/** 记录（或更新）一条阅读位置；同一 text 只保留最新一条，列表按时间倒序。 */
export function recordReading(entry: Omit<ReadingEntry, "ts">): void {
  if (!Number.isFinite(entry.textId) || entry.textId <= 0) return;
  if (!Number.isFinite(entry.juan) || entry.juan < 1) return;
  const rest = readAll().filter((e) => e.textId !== entry.textId);
  writeAll([{ ...entry, ratio: clamp01(entry.ratio), ts: Date.now() }, ...rest]);
}

/** 最近阅读列表（时间倒序，最多 MAX_ENTRIES 条）。 */
export function getReadingHistory(): ReadingEntry[] {
  return readAll();
}

/** 从最近阅读里删掉一部经（首页「最近阅读」的 × 按钮）。返回删除后的列表。 */
export function removeReading(textId: number): ReadingEntry[] {
  const rest = readAll().filter((e) => e.textId !== textId);
  writeAll(rest);
  return rest;
}

/**
 * 「3 天前」「昨天」这类相对时间，跟随界面语言（zh / zh-Hant / en）。
 * 一分钟内（含设备时钟回拨导致的未来时间）返回 justNow ——
 * Intl 在 0 秒时给的是「现在」/"now"，用作阅读时间不通顺。
 */
export function formatReadAgo(ts: number, now: number, lang: string, justNow: string): string {
  const sec = Math.max(0, Math.round((now - ts) / 1000));
  let rtf: Intl.RelativeTimeFormat;
  try {
    rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  } catch {
    rtf = new Intl.RelativeTimeFormat("zh", { numeric: "auto" });
  }
  if (sec < 60) return justNow;
  const min = Math.floor(sec / 60);
  if (min < 60) return rtf.format(-min, "minute");
  const hr = Math.floor(min / 60);
  if (hr < 24) return rtf.format(-hr, "hour");
  const day = Math.floor(hr / 24);
  if (day < 30) return rtf.format(-day, "day");
  const month = Math.floor(day / 30);
  if (month < 12) return rtf.format(-month, "month");
  return rtf.format(-Math.floor(month / 12), "year");
}

/** 某部经的上次阅读位置；无记录返回 null。 */
export function getLastPosition(textId: number): ReadingEntry | null {
  return readAll().find((e) => e.textId === textId) ?? null;
}

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.min(Math.max(n, 0), 1);
}
