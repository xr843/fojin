import { describe, it, expect } from "vitest";
import { findQuoteSpans } from "./citationMatch";

/**
 * LLM 缩写长引文时惯用省略号：「於無學法說純白聲……以無漏業非順愛故」。
 * 整条作为连续串在原文里并不存在（中间那段被省掉了），于是 findQuoteSpan
 * 匹配失败，抽屉退回到「高亮整个被引 chunk」——约 500 字、起止落在任意切块
 * 边界上，看起来就是高亮画错了（2026-07-29 用户反馈）。
 *
 * 拆开后每一段都能精确命中，所以这是可以精确高亮的。
 */
const HAY =
  "或無學法，於超一切染身中可得故，立純白名；非如學法，非超一切染身中可得故，" +
  "不名純白。故彼經中依如是義，於無學法說純白聲。今此經中以無漏業非順愛故，" +
  "又不能感白異熟故，說名非白。";

describe("findQuoteSpans", () => {
  it("整条能连续命中时返回单段", () => {
    const spans = findQuoteSpans(HAY, "於無學法說純白聲");
    expect(spans).toHaveLength(1);
    expect(HAY.slice(spans[0][0], spans[0][1])).toBe("於無學法說純白聲");
  });

  it("带省略号的引文按段命中，各段分别高亮", () => {
    const spans = findQuoteSpans(
      HAY,
      "於無學法說純白聲……以無漏業非順愛故，又不能感白異熟故，說名非白",
    );
    expect(spans.length).toBe(2);
    const marked = spans.map(([a, b]) => HAY.slice(a, b));
    expect(marked[0]).toContain("於無學法說純白聲");
    expect(marked[1]).toContain("說名非白");
    // 关键：省略掉的那段不得被一并涂黄
    const total = spans.reduce((n, [a, b]) => n + (b - a), 0);
    expect(total).toBeLessThan(HAY.length * 0.75);
  });

  it("三点式省略号（…/...）同样处理", () => {
    for (const dots of ["…", "..."]) {
      const spans = findQuoteSpans(HAY, `於無學法說純白聲${dots}說名非白`);
      expect(spans.length).toBe(2);
    }
  });

  it("分段过短的不予高亮——短串容易偶然命中，宁可不标", () => {
    const spans = findQuoteSpans(HAY, "於無學法說純白聲……故");
    expect(spans).toHaveLength(1);
  });

  it("完全对不上时返回空数组，让调用方走兜底", () => {
    expect(findQuoteSpans(HAY, "這段話原文裡並不存在無論如何")).toEqual([]);
  });

  it("返回的区间按位置升序且互不重叠", () => {
    const spans = findQuoteSpans(
      HAY,
      "於無學法說純白聲……以無漏業非順愛故，又不能感白異熟故，說名非白",
    );
    for (let i = 1; i < spans.length; i++) {
      expect(spans[i][0]).toBeGreaterThanOrEqual(spans[i - 1][1]);
    }
  });
});
