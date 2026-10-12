import { describe, expect, it } from "vitest";
import { clampSearchQuery, SEARCH_QUERY_MAX } from "./searchQuery";

// 用户 2026-10-12 截图里贴的那段：《瑜伽師地論》卷38（T1579）原文，远超 200 字。
const YOGA =
  "云何菩薩具多勝解？謂諸菩薩於其八種勝解依處，具足成就淨信為先決定喜樂。" +
  "一者、於三寶功德勝解依處，具足成就淨信為先決定喜樂。謂於佛法僧真實功德具多勝解。" +
  "二者、於佛菩薩威力勝解依處，具足成就淨信為先決定喜樂。謂於如前所說威力具多勝解。" +
  "三者、於真實義勝解依處，具足成就淨信為先決定喜樂。謂於如前所說真實義具多勝解。" +
  "四者、於因勝解依處，具足成就淨信為先決定喜樂。謂於種種如應所攝無顛倒因具多勝解。" +
  "五者、於果勝解依處，具足成就淨信為先決定喜樂。謂於種種如應所攝無顛倒果具多勝解。" +
  "六者、於應得義勝解依處，具足成就淨信為先決定喜樂。";

const len = (s: string) => Array.from(s).length;

describe("clampSearchQuery", () => {
  it("leaves queries within the limit untouched (trimmed)", () => {
    expect(clampSearchQuery("  般若  ")).toEqual({ text: "般若", truncated: false, total: 2 });
  });

  it("keeps a long pasted passage under the backend limit, cut at a sentence end", () => {
    expect(len(YOGA)).toBeGreaterThan(SEARCH_QUERY_MAX);
    const r = clampSearchQuery(YOGA);
    expect(r.truncated).toBe(true);
    expect(r.total).toBe(len(YOGA));
    expect(len(r.text)).toBeLessThanOrEqual(SEARCH_QUERY_MAX);
    expect(r.text.endsWith("。")).toBe(true);
    expect(YOGA.startsWith(r.text)).toBe(true);
    // 截断点不能太靠前：至少保留上限的 40%
    expect(len(r.text)).toBeGreaterThanOrEqual(SEARCH_QUERY_MAX * 0.4);
  });

  it("counts code points, not UTF-16 units (extension-B characters)", () => {
    // 𠀀 是扩展 B 区字，JS .length 为 2；后端按码点算 1。
    const q = "𠀀".repeat(SEARCH_QUERY_MAX);
    expect(q.length).toBe(SEARCH_QUERY_MAX * 2);
    expect(clampSearchQuery(q)).toEqual({ text: q, truncated: false, total: SEARCH_QUERY_MAX });
  });

  it("hard-cuts at the limit when there is no usable boundary", () => {
    const q = "般".repeat(SEARCH_QUERY_MAX + 50);
    const r = clampSearchQuery(q);
    expect(len(r.text)).toBe(SEARCH_QUERY_MAX);
  });

  it("falls back to a clause boundary when the only sentence end is too early", () => {
    const q = "如是。" + "我聞一時佛在".repeat(20) + "，" + "舍衛國".repeat(40);
    const r = clampSearchQuery(q);
    expect(r.text.endsWith("，")).toBe(true);
    expect(len(r.text)).toBeLessThanOrEqual(SEARCH_QUERY_MAX);
  });
});
