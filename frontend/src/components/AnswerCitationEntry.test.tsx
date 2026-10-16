/** 回答下方的引文面板入口胶囊：计数口径 / 只有参考经文 / 流式不显示 / 信任行不重复核验数。 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ChatMessageItem, ChatSource, ChatTrustStatus } from "../api/client";
import type { TextId } from "../types/branded";
import AnswerCitationEntry from "./AnswerCitationEntry";

const Q1 = "色不異空空不異色";
const Q2 = "色即是空空即是色";
const XIN: ChatSource = {
  text_id: 7 as TextId, juan_num: 1, chunk_index: 3,
  chunk_text: `觀自在菩薩……${Q1}，${Q2}，受想行識。`, score: 0.9, title_zh: "般若波羅蜜多心經",
};
const JIN: ChatSource = {
  text_id: 9 as TextId, juan_num: 2, chunk_index: 0, chunk_text: "如是我聞。", score: 0.5, title_zh: "金剛般若波羅蜜經",
};

const trust = (over: Partial<ChatTrustStatus> = {}): ChatTrustStatus => ({
  state: "verified", citation_count: 2, source_count: 2,
  citation_mutation_count: 0, quote_mutation_count: 0, quote_checked_count: 2,
  ...over,
});

function msg(over: Partial<ChatMessageItem> = {}): ChatMessageItem {
  return {
    id: 1,
    role: "assistant",
    // 心经第1卷被引两次（两句不同的引文）+ 金刚经第2卷一次 = 2 处出处
    content: `经云：「${Q1}」【《般若波罗蜜多心经》第1卷】。又「${Q2}」【《般若波罗蜜多心经》第1卷】。另见【《金刚般若波罗蜜经》第2卷】。`,
    sources: [XIN, JIN],
    created_at: "2026-10-16T02:00:00.000Z",
    trust_status: trust({
      quote_checked_count: 2,
      checked_quotes: [{ title: "般若波罗蜜多心经", juan: 1, quote: Q1 }, { title: "般若波罗蜜多心经", juan: 1, quote: Q2 }],
    }),
    ...over,
  };
}

const chip = () => document.querySelector<HTMLButtonElement>(".chat-cpanel-entry");

describe("AnswerCitationEntry", () => {
  it("counts distinct 出处 (text + fascicle), not rows; checked count comes from quote_checked_count", () => {
    render(<AnswerCitationEntry m={msg()} isStreaming={false} onOpen={vi.fn()} />);
    expect(chip()).toHaveTextContent("2 处出处 · 已逐字核验 2 条");
  });

  it("does not count the panel's supplemented checked-quote rows as extra citations", () => {
    // 一个【】标记，但核验表里有两句都在正文里 —— 面板会补一行，胶囊仍是 1 处出处。
    const m = msg({
      content: `经云：「${Q1}」，又说「${Q2}」【《般若波罗蜜多心经》第1卷】。`,
      sources: [XIN],
    });
    render(<AnswerCitationEntry m={m} isStreaming={false} onOpen={vi.fn()} />);
    expect(chip()).toHaveTextContent("1 处出处 · 已逐字核验 2 条");
  });

  it("without a checked count only says how many 出处", () => {
    const m = msg({ trust_status: trust({ quote_checked_count: null }) });
    render(<AnswerCitationEntry m={m} isStreaming={false} onOpen={vi.fn()} />);
    expect(chip()!.textContent).toBe("2 处出处");
  });

  it("only retrieved sources, no explicit citation → no chip (the 参考经文 chips row already covers it)", () => {
    const m = msg({ content: "这是转述，没有标出处。", trust_status: trust({ state: "sources_available", quote_checked_count: 0 }) });
    render(<AnswerCitationEntry m={m} isStreaming={false} onOpen={vi.fn()} />);
    expect(chip()).toBeNull();
  });

  it("is not shown while streaming", () => {
    const { container } = render(<AnswerCitationEntry m={msg()} isStreaming onOpen={vi.fn()} />);
    expect(container.innerHTML).toBe("");
  });

  it("no citations and no sources: no chip, the trust line stays as before", () => {
    const m = msg({ content: "无出处。", sources: null, trust_status: trust({ state: "no_sources", quote_checked_count: 0 }) });
    render(<AnswerCitationEntry m={m} isStreaming={false} onOpen={vi.fn()} />);
    expect(chip()).toBeNull();
    expect(screen.getByText("未检索到可点击出处")).toBeInTheDocument();
  });

  it("keeps the trust state next to the chip but drops the duplicated checked count", () => {
    const { container } = render(<AnswerCitationEntry m={msg()} isStreaming={false} onOpen={vi.fn()} />);
    expect(screen.getByText("引用已校验")).toBeInTheDocument();
    expect(container.textContent).not.toContain("已逐字核验 2 条引文");
  });

  it("keeps the 'no verbatim quote' clarification — the chip does not say it", () => {
    const m = msg({ trust_status: trust({ quote_checked_count: 0 }) });
    const { container } = render(<AnswerCitationEntry m={m} isStreaming={false} onOpen={vi.fn()} />);
    expect(container.textContent).toContain("本答案未含逐字引文");
  });

  it("click hands back this very message", () => {
    const onOpen = vi.fn();
    const m = msg();
    render(<AnswerCitationEntry m={m} isStreaming={false} onOpen={onOpen} />);
    fireEvent.click(chip()!);
    expect(onOpen).toHaveBeenCalledWith(m);
  });
});
