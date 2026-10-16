import { describe, expect, it } from "vitest";
import type { ChatMessageItem, ChatSource } from "../api/client";
import type { TextId } from "../types/branded";
import {
  distinctSourceTextCount,
  extractAnswerCitations,
  findAnswerForTarget,
} from "./answerCitations";

const QUOTE = "色不異空空不異色色即是空空即是色";
const SOURCES: ChatSource[] = [
  {
    text_id: 7 as TextId,
    juan_num: 1,
    chunk_index: 3,
    chunk_text: `觀自在菩薩……${QUOTE}，受想行識亦復如是。`,
    score: 0.9,
    title_zh: "般若波羅蜜多心經",
  },
  {
    text_id: 9 as TextId,
    juan_num: 2,
    chunk_index: 0,
    chunk_text: "如是我聞。",
    score: 0.5,
    title_zh: "金剛般若波羅蜜經",
  },
];

const ANSWER =
  `经云：「${QUOTE}」【《般若波罗蜜多心经》第1卷】。\n` +
  "又见【《金刚般若波罗蜜经》第2卷】。\n" +
  `重复一次：「${QUOTE}」【《般若波罗蜜多心经》第1卷】。\n` +
  "另提《金刚般若波罗蜜经》一名。";

describe("extractAnswerCitations", () => {
  it("lists explicit citations in order, deduplicated, skipping bare title mentions", () => {
    const rows = extractAnswerCitations(ANSWER, SOURCES, "zh");
    expect(rows.map((r) => [r.target.textId, r.target.juanNum, r.target.chunkIndex])).toEqual([
      [7, 1, 3],
      [9, 2, 0],
    ]);
    expect(rows[0].target.quote).toBe(QUOTE);
    expect(rows[1].target.quote).toBeUndefined();
  });

  it("marks a row verbatim-checked ONLY when the backend listed that exact passage", () => {
    const checked = [{ title: "般若波罗蜜多心经", juan: 1, quote: QUOTE }];
    const rows = extractAnswerCitations(ANSWER, SOURCES, "zh", checked);
    expect(rows.map((r) => r.verbatimChecked)).toEqual([true, false]);
  });

  it("never marks anything checked when the backend list is absent", () => {
    // quote_checked_count may say 1, but without the list nothing is per-row known.
    const rows = extractAnswerCitations(ANSWER, SOURCES, "zh", null);
    expect(rows.some((r) => r.verbatimChecked)).toBe(false);
  });

  it("does not mark a row whose quote differs from the listed one", () => {
    const checked = [{ title: "般若波罗蜜多心经", juan: 1, quote: "别的一段别的一段别的一段" }];
    const rows = extractAnswerCitations(ANSWER, SOURCES, "zh", checked);
    expect(rows[0].verbatimChecked).toBe(false);
  });

  it("returns nothing without sources (nothing is clickable inline either)", () => {
    expect(extractAnswerCitations(ANSWER, null, "zh")).toEqual([]);
  });
});

describe("distinctSourceTextCount", () => {
  it("counts texts, not chunks", () => {
    expect(distinctSourceTextCount([...SOURCES, { ...SOURCES[0], chunk_index: 4 }])).toBe(2);
    expect(distinctSourceTextCount(null)).toBe(0);
  });
});

describe("findAnswerForTarget", () => {
  const older: ChatMessageItem = {
    id: 1, role: "assistant", content: ANSWER, sources: SOURCES, created_at: "2026-10-16T01:00:00Z",
  };
  const newer: ChatMessageItem = {
    id: 3, role: "assistant", content: "无引文。", sources: [SOURCES[1]], created_at: "2026-10-16T02:00:00Z",
  };
  const msgs = [older, { ...older, id: 2, role: "user", content: "问" }, newer];

  it("finds the answer whose citation was clicked", () => {
    const target = { textId: 7, juanNum: 1, chunkIndex: 3, titleZh: "般若波罗蜜多心经", quote: QUOTE };
    expect(findAnswerForTarget(msgs, target, "zh")).toBe(older);
  });

  it("falls back to retrieved sources for chip clicks, newest first", () => {
    const target = { textId: 9, juanNum: 2, chunkIndex: 0, titleZh: "" };
    expect(findAnswerForTarget(msgs, target, "zh")).toBe(newer);
    expect(findAnswerForTarget(msgs, target, "zh", older)).toBe(older);
  });
});

describe("extractAnswerCitations — checked quote that is not the one nearest the marker", () => {
  // 生产实例（会话 3652）：后端核验了同一段里较早的那句，面板只展示了紧贴标记的那句，
  // 于是「已逐字核验 3 条」配 1 个徽章。核验过的句子必须在面板上以自己的一行出现并带徽章。
  const EARLY = "觀自在菩薩行深般若波羅蜜多時";
  const ANS = `经文先说「${EARLY}」，接着说「${QUOTE}」【《般若波罗蜜多心经》第1卷】。`;
  const SRC: ChatSource[] = [{ ...SOURCES[0], chunk_text: `${EARLY}，照見五蘊皆空……${QUOTE}。` }];

  it("adds the checked quote as its own badged row under the same citation", () => {
    const checked = [{ title: "般若波罗蜜多心经", juan: 1, quote: EARLY }];
    const rows = extractAnswerCitations(ANS, SRC, "zh", checked);
    const early = rows.find((r) => r.target.quote === EARLY);
    expect(early).toBeDefined();
    expect(early!.verbatimChecked).toBe(true);
    expect([early!.target.textId, early!.target.juanNum, early!.target.chunkIndex]).toEqual([7, 1, 3]);
    // 紧贴标记的那句没被核验，仍不带徽章
    expect(rows.find((r) => r.target.quote === QUOTE)?.verbatimChecked).toBe(false);
    expect(rows.filter((r) => r.verbatimChecked)).toHaveLength(1);
  });

  it("does not invent a row for a checked quote absent from the answer or under another fascicle", () => {
    const checked = [
      { title: "般若波罗蜜多心经", juan: 1, quote: "答案里根本没有这一句话" },
      { title: "般若波罗蜜多心经", juan: 9, quote: EARLY },
    ];
    const rows = extractAnswerCitations(ANS, SRC, "zh", checked);
    expect(rows.some((r) => r.verbatimChecked)).toBe(false);
    expect(rows).toHaveLength(1);
  });
});
