import { describe, expect, it } from "vitest";
import { lunarLabel, LUNAR_TABLE_UNTIL } from "./lunar";

describe("农历", () => {
  it("今天与月份边界", () => {
    expect(lunarLabel("2026-11-24")).toBe("十月十六");
    expect(lunarLabel("2026-12-09")).toBe("冬月初一");
  });

  it("春节按权威万年历（浏览器 Intl 农历在 2027、2030 年会错一天）", () => {
    expect(lunarLabel("2027-02-05")).toBe("腊月廿九");
    expect(lunarLabel("2027-02-06")).toBe("正月初一");
    expect(lunarLabel("2030-02-02")).toBe("腊月三十");
    expect(lunarLabel("2030-02-03")).toBe("正月初一");
  });

  it("闰月与日名", () => {
    expect(lunarLabel("2028-06-23")).toBe("闰五月初一");
    expect(lunarLabel("2028-06-12")).toBe("五月二十");
    expect(lunarLabel("2026-03-08")).toBe("正月二十");
  });

  it("超出表的日期不显示，不猜", () => {
    expect(lunarLabel("2031-03-01")).toBeNull();
  });

  it("月表至少还能用一年——到期前这里会红，提醒重跑 backend/scripts/build_lunar_months.py", () => {
    const oneYearLater = new Date(Date.now() + 365 * 86_400_000).toISOString().slice(0, 10);
    expect(oneYearLater < LUNAR_TABLE_UNTIL).toBe(true);
  });
});
