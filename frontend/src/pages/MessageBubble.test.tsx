import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { Components } from "react-markdown";
import { MessageBubble } from "./ChatPage";
import type { ChatMessageItem, ChatSource } from "../api/client";
import type { TextId } from "../types/branded";

// antd (Button/Tooltip) reads matchMedia via useBreakpoint under jsdom.
beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
});

const markdownComponents = {} as Components;

function msg(o: Partial<ChatMessageItem> = {}): ChatMessageItem {
  return { id: 1, role: "assistant", content: "answer", sources: null, created_at: "2026-06-18", ...o };
}

function src(o: Partial<ChatSource> = {}): ChatSource {
  return {
    text_id: 1 as TextId,
    juan_num: 1,
    chunk_index: 0,
    chunk_text: "色不異空",
    score: 0.9,
    title_zh: "心經",
    ...o,
  };
}

function renderBubble(props: Partial<React.ComponentProps<typeof MessageBubble>> = {}) {
  const onSuggestionClick = vi.fn();
  const onShare = vi.fn();
  const onRetry = vi.fn();
  const onFeedback = vi.fn();
  const onSourceClick = vi.fn();
  render(
    <MessageBubble
      m={msg()}
      isStreaming={false}
      sending={false}
      user={null}
      markdownComponents={markdownComponents}
      onSuggestionClick={onSuggestionClick}
      onShare={onShare}
      onRetry={onRetry}
      onFeedback={onFeedback}
      onSourceClick={onSourceClick}
      {...props}
    />,
  );
  return { onSuggestionClick, onShare, onRetry, onFeedback, onSourceClick };
}

describe("MessageBubble", () => {
  it("renders an assistant message's markdown content", () => {
    renderBubble({ m: msg({ content: "唯识无境的核心是什么" }) });
    expect(screen.getByText(/唯识无境的核心是什么/)).toBeInTheDocument();
  });

  it("shows the streaming ▌ cursor while streaming", () => {
    const { container } = render(
      <MessageBubble
        m={msg({ content: "正在生成" })} isStreaming sending user={null}
        markdownComponents={markdownComponents}
        onSuggestionClick={vi.fn()} onShare={vi.fn()} onRetry={vi.fn()} onFeedback={vi.fn()} onSourceClick={vi.fn()}
      />,
    );
    expect(container.textContent).toContain("▌");
  });

  it("renders a user message verbatim (no markdown/follow-up processing)", () => {
    renderBubble({ m: msg({ role: "user", content: "[追问] 这行不应被当作建议" }) });
    // The user's literal text — including the bracket — is shown as-is.
    expect(screen.getByText(/这行不应被当作建议/)).toBeInTheDocument();
  });

  it("renders the thinking indicator for the THINKING sentinel", () => {
    // content must be the exact THINKING_SENTINEL to take the thinking branch;
    // assert the structural .chat-thinking marker (language-independent).
    renderBubble({ m: msg({ content: "正在检索经文并生成回答..." }) });
    expect(document.querySelector(".chat-thinking")).not.toBeNull();
  });

  it("renders follow-up suggestions and fires onSuggestionClick", () => {
    const { onSuggestionClick } = renderBubble({
      m: msg({ content: "答案正文\n[追问] 什么是阿赖耶识" }),
    });
    const chip = screen.getByText("什么是阿赖耶识");
    fireEvent.click(chip);
    expect(onSuggestionClick).toHaveBeenCalledWith("什么是阿赖耶识");
  });

  it("renders a concise verified citation trust hint", () => {
    renderBubble({
      m: msg({
        trust_status: {
          state: "verified",
          citation_count: 1,
          source_count: 1,
          citation_mutation_count: 0,
          quote_mutation_count: 0,
          max_source_score: 0.91,
          min_source_score: 0.91,
        },
      } as Partial<ChatMessageItem>),
    });

    expect(screen.getByText("引用已校验")).toBeInTheDocument();
  });

  it("wires the share button to onShare with the message", () => {
    const m = msg({ id: 7, content: "可分享的回答" });
    // assistant, not failed, no user → action row is [copy, share]
    const { onShare } = renderBubble({ m });
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[1]); // share
    expect(onShare).toHaveBeenCalledWith(m);
  });

  it("hides feedback for an in-flight (placeholder-id) assistant message", () => {
    // id ≥ 1e12 is the Date.now() placeholder before the real chat_messages.id
    // arrives; feedback would PUT to a nonexistent id, so it's hidden.
    renderBubble({ m: msg({ id: 1.7e12 }), user: { id: 9 } as never });
    expect(screen.getAllByRole("button")).toHaveLength(2); // copy + share only
  });

  it("shows feedback for a saved assistant message + user and fires onFeedback", () => {
    const { onFeedback } = renderBubble({ m: msg({ id: 42 }), user: { id: 9 } as never });
    const buttons = screen.getAllByRole("button"); // copy, share, like, dislike
    expect(buttons).toHaveLength(4);
    fireEvent.click(buttons[2]); // like
    expect(onFeedback).toHaveBeenCalledWith(expect.objectContaining({ id: 42 }), "up");
  });

  it("renders a persistent 参考经文 source list and fires onSourceClick", () => {
    const s = src({ text_id: 5 as TextId, juan_num: 16, title_zh: "雜阿含經" });
    const { onSourceClick } = renderBubble({ m: msg({ sources: [s] }) });
    // Label + a clickable chip for the retrieved source, even though the answer
    // text never named it inline.
    expect(screen.getByText("参考经文")).toBeInTheDocument();
    const chip = screen.getByText("《雜阿含經》 第16卷");
    fireEvent.click(chip);
    expect(onSourceClick).toHaveBeenCalledWith(expect.objectContaining({ text_id: 5, juan_num: 16 }));
  });

  it("dedupes the source list by text + fascicle", () => {
    renderBubble({
      m: msg({
        sources: [
          src({ text_id: 1 as TextId, juan_num: 1, chunk_index: 0, title_zh: "心經" }),
          src({ text_id: 1 as TextId, juan_num: 1, chunk_index: 3, title_zh: "心經" }), // same 卷, other chunk
          src({ text_id: 2 as TextId, juan_num: 1, title_zh: "金剛經" }),
        ],
      }),
    });
    expect(screen.getAllByText("《心經》 第1卷")).toHaveLength(1);
    expect(screen.getByText("《金剛經》 第1卷")).toBeInTheDocument();
  });

  it("shows no source list when the answer has no retrieved sources", () => {
    renderBubble({ m: msg({ sources: null }) });
    expect(screen.queryByText("参考经文")).toBeNull();
  });

  it("skips sources without a title (nothing to label the chip with)", () => {
    renderBubble({ m: msg({ sources: [src({ title_zh: undefined })] }) });
    expect(screen.queryByText("参考经文")).toBeNull();
  });
});
