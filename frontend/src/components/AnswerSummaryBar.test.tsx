import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ChatMessageItem, ChatSource } from "../api/client";
import type { TextId } from "../types/branded";
import AnswerSummaryBar from "./AnswerSummaryBar";

const src = (text_id: number, chunk_index: number): ChatSource => ({
  text_id: text_id as TextId, juan_num: 1, chunk_index, chunk_text: "x", score: 0.5, title_zh: `T${text_id}`,
});

function msg(over: Partial<ChatMessageItem> = {}): ChatMessageItem {
  return {
    id: 1,
    role: "assistant",
    content: "答。",
    sources: [src(1, 0), src(1, 1), src(2, 0)],
    created_at: "2026-10-16T00:00:00Z",
    trust_status: {
      state: "verified", citation_count: 3, source_count: 3,
      citation_mutation_count: 0, quote_mutation_count: 0, quote_checked_count: 7,
    },
    ...over,
  };
}

describe("AnswerSummaryBar", () => {
  it("summarises texts searched, quotes checked and time for a fresh answer", () => {
    render(<AnswerSummaryBar m={msg({ totalMs: 26_000 })} isStreaming={false} />);
    expect(screen.getByText("检索 2 部经典 · 核验 7 条引文 · 用时 26.0 秒")).toBeInTheDocument();
  });

  it("drops the time segment for history answers (totalMs not persisted) — no 0, no crash", () => {
    const { container } = render(<AnswerSummaryBar m={msg()} isStreaming={false} />);
    expect(container.textContent).toBe("检索 2 部经典 · 核验 7 条引文");
    expect(container.textContent).not.toMatch(/用时/);
  });

  it("omits a zero / unknown checked count instead of saying 核验 0", () => {
    const m = msg({ totalMs: 5_000 });
    m.trust_status = { ...m.trust_status!, quote_checked_count: 0 };
    const { container, rerender } = render(<AnswerSummaryBar m={m} isStreaming={false} />);
    expect(container.textContent).toBe("检索 2 部经典 · 用时 5.0 秒");
    rerender(<AnswerSummaryBar m={{ ...m, trust_status: null }} isStreaming={false} />);
    expect(container.textContent).toBe("检索 2 部经典 · 用时 5.0 秒");
  });

  it("renders nothing when there is nothing true to say, and nothing while streaming", () => {
    const { container, rerender } = render(
      <AnswerSummaryBar m={msg({ sources: null, trust_status: null })} isStreaming={false} />,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(<AnswerSummaryBar m={msg({ totalMs: 1000 })} isStreaming />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is collapsed by default and reveals the reasoning on demand", () => {
    render(<AnswerSummaryBar m={msg({ totalMs: 26_000, reasoningFinal: "先查心经出处。" })} isStreaming={false} />);
    const toggle = screen.getByRole("button", { expanded: false });
    expect(screen.queryByText("先查心经出处。")).toBeNull();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("先查心经出处。")).toBeInTheDocument();
    // still labelled as not-the-answer
    expect(screen.getByText(/非最终回答/)).toBeInTheDocument();
  });
});
