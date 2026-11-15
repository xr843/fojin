import { beforeEach, describe, expect, it } from "vitest";
import { formatReadAgo, getReadingHistory, recordReading, removeReading } from "./readingHistory";

describe("removeReading", () => {
  beforeEach(() => localStorage.clear());

  it("只删指定那部经，其余顺序不变，且写回存储", () => {
    recordReading({ textId: 1, title: "甲", juan: 1, ratio: 0 });
    recordReading({ textId: 2, title: "乙", juan: 3, ratio: 0 });
    recordReading({ textId: 3, title: "丙", juan: 5, ratio: 0 });

    const rest = removeReading(2);

    expect(rest.map((e) => e.textId)).toEqual([3, 1]);
    expect(getReadingHistory().map((e) => e.textId)).toEqual([3, 1]);
  });

  it("删不存在的 id 不改动列表", () => {
    recordReading({ textId: 1, title: "甲", juan: 1, ratio: 0 });
    expect(removeReading(99).map((e) => e.textId)).toEqual([1]);
  });
});

describe("formatReadAgo", () => {
  const now = Date.UTC(2026, 10, 15, 12, 0, 0);
  const ago = (sec: number) => now - sec * 1000;

  it("中文各档", () => {
    expect(formatReadAgo(ago(10), now, "zh", "刚刚")).toBe("刚刚");
    expect(formatReadAgo(ago(5 * 60), now, "zh", "刚刚")).toBe("5分钟前");
    expect(formatReadAgo(ago(3 * 3600), now, "zh", "刚刚")).toBe("3小时前");
    expect(formatReadAgo(ago(26 * 3600), now, "zh", "刚刚")).toBe("昨天");
    expect(formatReadAgo(ago(3 * 86400), now, "zh", "刚刚")).toBe("3天前");
    expect(formatReadAgo(ago(65 * 86400), now, "zh", "刚刚")).toBe("2个月前");
  });

  it("繁体与英文跟随界面语言", () => {
    expect(formatReadAgo(ago(3 * 86400), now, "zh-Hant", "剛剛")).toBe("3 天前");
    expect(formatReadAgo(ago(3 * 86400), now, "en", "just now")).toBe("3 days ago");
  });

  it("未来时间（设备时钟回拨）不显示成「X 天后」", () => {
    expect(formatReadAgo(now + 3600_000, now, "zh", "刚刚")).toBe("刚刚");
  });
});
