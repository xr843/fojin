import { beforeAll, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Components } from "react-markdown";
import i18n from "../i18n";
import { MessageBubble } from "./ChatPage";
import { formatResponseSeconds } from "../utils/responseTiming";
import type { ChatMessageItem } from "../api/client";

/**
 * 每条回答显示它花了多久。
 *
 * 分成两个数是因为等待并不平均：生产实测第一个字要 24-180 秒，之后逐字流出很快，
 * 所以「首字」才是用户真正在等的那一段，而「共」是这次问答的总代价。
 *
 * 只对**本次会话生成的**回答显示。判据是 totalMs 的有无——历史消息从后端读回来
 * 时没有这个字段（它和 retrieval / reasoningSince 一样不持久化），于是刷新之后
 * 那一行自然消失，而不是显示一个没人计过的时间。
 */

beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = (q: string) => ({
      matches: false, media: q, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
  }
});

const noop = () => {};

function renderBubble(overrides: Partial<ChatMessageItem>) {
  const m: ChatMessageItem = {
    id: 1,
    role: "assistant",
    content: "《胜鬘经》在如来藏系经典中具有承上启下的枢纽地位。",
    sources: null,
    created_at: "2026-08-21T09:00:00Z",
    ...overrides,
  };
  return render(
    <MessageBubble
      m={m}
      isStreaming={false}
      sending={false}
      user={null}
      markdownComponents={{} as Components}
      onSuggestionClick={noop}
      onShare={noop}
      onRetry={noop}
      onContinue={noop}
      onRegenerate={noop}
      onFeedback={noop}
      onSourceClick={noop}
    />,
  );
}

describe("formatResponseSeconds", () => {
  it("keeps one decimal under a minute", () => {
    // 短的那些差半秒是能感觉到的。
    expect(formatResponseSeconds(12_340)).toBe("12.3");
    expect(formatResponseSeconds(900)).toBe("0.9");
  });

  it("drops the decimal past a minute", () => {
    // 「共 182.0 秒」里那个 .0 只是噪音。
    expect(formatResponseSeconds(182_400)).toBe("182");
    expect(formatResponseSeconds(60_000)).toBe("60");
  });

  it("rounds rather than truncates at the boundary", () => {
    // 59.97 秒该读作 60.0 秒，不该读作 59.9 秒。
    expect(formatResponseSeconds(59_970)).toBe("60.0");
  });

  it("does not crash on zero", () => {
    expect(formatResponseSeconds(0)).toBe("0.0");
  });
});

describe("timing line", () => {
  it("shows first-word and total for an answer generated this session", async () => {
    await i18n.changeLanguage("zh");
    renderBubble({ firstTokenMs: 12_340, totalMs: 48_600 });
    expect(screen.getByText(/首字 12\.3 秒/)).toBeInTheDocument();
    expect(screen.getByText(/共 48\.6 秒/)).toBeInTheDocument();
  });

  it("is absent on a history message read back from the server", async () => {
    await i18n.changeLanguage("zh");
    // 历史消息没有 totalMs —— 这正是「这条不是本次会话生成的」的判据。
    renderBubble({});
    expect(screen.queryByText(/秒/)).not.toBeInTheDocument();
  });

  it("is absent on a failed answer", async () => {
    await i18n.changeLanguage("zh");
    // 给「请求失败，请重试」标上用了多少秒，是拿噪音充信息。
    renderBubble({ content: "请求失败，请重试", firstTokenMs: null, totalMs: 3_200 });
    expect(screen.queryByText(/共 3\.2 秒/)).not.toBeInTheDocument();
  });

  it("shows only the total when no token ever arrived", async () => {
    await i18n.changeLanguage("zh");
    // 空回复被兜底转成失败哨兵，所以这里测的是「有正文但首字没记到」的边界：
    // 不能因为 firstTokenMs 为空就把整行吞掉。
    renderBubble({ content: "一段回答。", firstTokenMs: null, totalMs: 7_000 });
    expect(screen.getByText(/共 7\.0 秒/)).toBeInTheDocument();
    expect(screen.queryByText(/首字/)).not.toBeInTheDocument();
  });

  it("never appears on the user's own message", async () => {
    await i18n.changeLanguage("zh");
    renderBubble({ role: "user", content: "《胜鬘经》一乘如来藏怎么讲？", totalMs: 48_600 });
    expect(screen.queryByText(/共 48\.6 秒/)).not.toBeInTheDocument();
  });
});
