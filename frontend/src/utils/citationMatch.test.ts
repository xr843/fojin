import { describe, it, expect } from "vitest";
import {
  normalizeForMatch,
  extractPrecedingQuote,
  pickSourceForQuote,
  findQuoteSpan,
} from "./citationMatch";
import type { ChatSource } from "../api/client";

function src(partial: Partial<ChatSource>): ChatSource {
  return {
    text_id: 1 as ChatSource["text_id"],
    juan_num: 1,
    chunk_index: 0,
    chunk_text: "",
    score: 0,
    title_zh: "测试",
    ...partial,
  } as ChatSource;
}

describe("normalizeForMatch", () => {
  it("folds 繁→简 and strips punctuation", () => {
    // 繁: 以五事交擾，渾濁真性  简(input): 以五事交扰，浑浊真性
    expect(normalizeForMatch("以五事交擾，渾濁真性")).toBe(
      normalizeForMatch("以五事交扰，浑浊真性"),
    );
  });
});

describe("extractPrecedingQuote", () => {
  it("pulls a 「」 quote sitting before a marker", () => {
    const before = "蓮池大師說「以五事交扰，浑浊真性，故名恶世」";
    expect(extractPrecedingQuote(before)).toBe("以五事交扰，浑浊真性，故名恶世");
  });
  it("pulls a curly-quote passage with a short gap before the marker", () => {
    const before = '答案中提到“以五事交扰，浑浊真性”，可见';
    expect(extractPrecedingQuote(before)).toBe("以五事交扰，浑浊真性");
  });
  it("returns null when there is no nearby quote", () => {
    expect(extractPrecedingQuote("这一段没有任何引号内容")).toBeNull();
  });
});

describe("pickSourceForQuote", () => {
  const candidates = [
    src({ chunk_index: 12, score: 0.9, chunk_text: "前略……不相干的高分内容……" }),
    src({ chunk_index: 50, score: 0.4, chunk_text: "……以五事交擾，渾濁真性，故名惡世……" }),
  ];

  it("picks the chunk containing the quote, not the top-scored one", () => {
    const picked = pickSourceForQuote(candidates, "以五事交扰，浑浊真性，故名恶世");
    expect(picked?.chunk_index).toBe(50);
  });

  it("returns null when no chunk contains the quote", () => {
    expect(pickSourceForQuote(candidates, "完全不存在的另一句话内容")).toBeNull();
  });

  it("returns null for an empty quote", () => {
    expect(pickSourceForQuote(candidates, null)).toBeNull();
  });
});

describe("findQuoteSpan", () => {
  it("locates a simplified quote inside traditional source text", () => {
    const hay = "如經所言，以五事交擾，渾濁真性，故名惡世，眾生難度。";
    const span = findQuoteSpan(hay, "以五事交扰，浑浊真性，故名恶世");
    expect(span).not.toBeNull();
    expect(hay.slice(span![0], span![1])).toBe("以五事交擾，渾濁真性，故名惡世");
  });

  it("tolerates punctuation differences between quote and source", () => {
    const hay = "以五事交擾渾濁真性故名惡世"; // source has no commas
    const span = findQuoteSpan(hay, "以五事交扰，浑浊真性，故名恶世");
    expect(span).not.toBeNull();
    expect(hay.slice(span![0], span![1])).toBe("以五事交擾渾濁真性故名惡世");
  });

  it("returns null when the quote is absent", () => {
    expect(findQuoteSpan("一段无关的原文", "以五事交扰，浑浊真性")).toBeNull();
  });
});
