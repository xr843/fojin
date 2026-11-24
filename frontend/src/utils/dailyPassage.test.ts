import { describe, expect, it } from "vitest";
import { beijingDateKey, dailyIndex, pickDaily, DAILY_PASSAGES, type DailyPassage } from "./dailyPassage";
import { wrapCjk } from "./shareCard";

const P = (n: number): DailyPassage => ({
  text: `段${n}`, title_zh: "經", cbeta_id: `T${n}`, text_id: n, juan_num: 1, reader_path: `/texts/${n}/read?juan=1`,
});

describe("每日一段", () => {
  it("按北京时间切日：UTC 16:00 已是北京第二天", () => {
    expect(beijingDateKey(new Date("2026-11-24T15:59:00Z"))).toBe("2026-11-24");
    expect(beijingDateKey(new Date("2026-11-24T16:00:00Z"))).toBe("2026-11-25");
  });

  it("同一天同一段，相邻两天不同段，按池子长度循环", () => {
    const pool = [P(1), P(2), P(3)];
    const a = pickDaily(new Date("2026-11-24T01:00:00Z"), pool);
    const b = pickDaily(new Date("2026-11-24T12:00:00Z"), pool);
    const c = pickDaily(new Date("2026-11-25T01:00:00Z"), pool);
    expect(a.passage).toBe(b.passage);
    expect(c.passage).not.toBe(a.passage);
    expect(dailyIndex("2026-01-01", 3)).toBe(0);
    expect(dailyIndex("2026-01-04", 3)).toBe(0);
    expect(dailyIndex("2025-12-31", 3)).toBe(2); // 起点之前也不出负数
  });

  it("段落池里每条都带站内阅读器链接与出处", () => {
    expect(DAILY_PASSAGES.length).toBeGreaterThanOrEqual(30);
    for (const p of DAILY_PASSAGES) {
      expect(p.reader_path).toMatch(/^\/texts\/\d+\/read\?juan=\d+/);
      expect(p.title_zh && p.cbeta_id && p.text).toBeTruthy();
    }
    // 相邻两条不是同一部经（生成时已按经打散）
    for (let i = 1; i < DAILY_PASSAGES.length; i++) {
      if (DAILY_PASSAGES[i].cbeta_id === DAILY_PASSAGES[i - 1].cbeta_id) {
        // 只有某部经条目多到轮不开时才允许相邻，且只能发生在末尾
        expect(i).toBeGreaterThan(DAILY_PASSAGES.length - 4);
      }
    }
  });
});

describe("分享图断行", () => {
  const measure = (s: string) => Array.from(s).length * 10;

  it("按宽度断行", () => {
    expect(wrapCjk(measure, "一二三四五六七", 30)).toEqual(["一二三", "四五六", "七"]);
  });

  it("优先在逗号处换行，不把半个词留在行尾", () => {
    // 每行最多 13 字：逐字断会成「一切有為法，如夢幻泡影，如」+「露亦如電，應作如是觀」
    expect(wrapCjk(measure, "一切有為法，如夢幻泡影，如露亦如電，應作如是觀", 130)).toEqual([
      "一切有為法，如夢幻泡影，",
      "如露亦如電，應作如是觀",
    ]);
  });

  it("标点不放行首，跟在上一行末尾", () => {
    expect(wrapCjk(measure, "一二三，四五", 30)).toEqual(["一二三，", "四五"]);
  });
});
