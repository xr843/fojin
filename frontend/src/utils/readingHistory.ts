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
  const rest = readAll().filter((e) => e.textId !== entry.textId);
  writeAll([{ ...entry, ratio: clamp01(entry.ratio), ts: Date.now() }, ...rest]);
}

/** 最近阅读列表（时间倒序，最多 MAX_ENTRIES 条）。 */
export function getReadingHistory(): ReadingEntry[] {
  return readAll();
}

/** 某部经的上次阅读位置；无记录返回 null。 */
export function getLastPosition(textId: number): ReadingEntry | null {
  return readAll().find((e) => e.textId === textId) ?? null;
}

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.min(Math.max(n, 0), 1);
}
