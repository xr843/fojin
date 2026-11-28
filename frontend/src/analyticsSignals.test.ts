import { describe, expect, it } from "vitest";
import { ENGAGE_MIN_MS, sectionOf, shouldEngage } from "./analyticsSignals";

describe("统计信号：板块归属", () => {
  it("各板块路径归到看板用的板块名", () => {
    expect(sectionOf("/chat")).toBe("chat");
    expect(sectionOf("/texts/76/read")).toBe("read");
    expect(sectionOf("/read")).toBe("read");
    expect(sectionOf("/texts/76")).toBe("texts");
    expect(sectionOf("/dictionary")).toBe("dict");
    expect(sectionOf("/dict/般若")).toBe("dict");
    expect(sectionOf("/sources")).toBe("sources");
    expect(sectionOf("/history")).toBe("history");
    expect(sectionOf("/search")).toBe("search");
    expect(sectionOf("/")).toBe("home");
    expect(sectionOf("/profile")).toBe("other");
  });
});

describe("统计信号：有效访问", () => {
  it("只认真人输入（isTrusted）、页面开够 3 秒、每板块每会话一次", () => {
    const sent = new Set<string>();
    expect(shouldEngage(false, ENGAGE_MIN_MS + 1, "read", sent)).toBe(false); // 程序模拟的点击
    expect(shouldEngage(true, ENGAGE_MIN_MS - 1, "read", sent)).toBe(false); // 刚打开就点
    expect(shouldEngage(true, ENGAGE_MIN_MS, "read", sent)).toBe(true);
    sent.add("read");
    expect(shouldEngage(true, 60_000, "read", sent)).toBe(false); // 已记过
    expect(shouldEngage(true, 60_000, "dict", sent)).toBe(true); // 换板块再记一次
  });
});
