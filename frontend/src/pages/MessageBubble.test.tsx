import { describe, it, expect, vi, beforeAll, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { Components } from "react-markdown";
import i18n from "../i18n";
import zhHantTranslation from "../../public/locales/zh-Hant/translation.json";
import { MessageBubble } from "./ChatPage";
import type { ChatMessageItem, ChatSource } from "../api/client";
import type { TextId } from "../types/branded";

// antd (Button/Tooltip) reads matchMedia via useBreakpoint under jsdom.
beforeAll(() => {
  // 只有 zh 被内联进 i18n 实例，其余走 HttpBackend——在 jsdom 里永远不 resolve。
  // 切到 zh-Hant 的用例必须先把包预置进去，否则 changeLanguage() 挂到超时。
  i18n.addResourceBundle("zh-Hant", "translation", zhHantTranslation, true, true);
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
});

// 语言是 i18n 单例上的全局状态：切过 zh-Hant 的用例必须还原，否则会漏进同
// 一 worker 里后续的用例（和后续的测试文件）。
afterEach(async () => {
  if (i18n.language !== "zh") await i18n.changeLanguage("zh");
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
      onContinue={vi.fn()}
      onRegenerate={vi.fn()}
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
        onSuggestionClick={vi.fn()} onShare={vi.fn()} onRetry={vi.fn()} onContinue={vi.fn()} onRegenerate={vi.fn()} onFeedback={vi.fn()} onSourceClick={vi.fn()}
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

  it("哨兵 + reasoningText → 渲染思考片段活窗（带非回答标签）", async () => {
    renderBubble({
      m: msg({
        content: "正在检索经文并生成回答...",
        reasoningText: "先查《心經》的出處",
      }),
    });
    const excerpt = document.querySelector(".chat-reasoning-excerpt");
    expect(excerpt).not.toBeNull();
    // 打字机逐字吐出（约 33ms/字），等它追平
    await waitFor(
      () => expect(excerpt!.textContent).toContain("先查《心經》的出處"),
      { timeout: 3000 },
    );
    // 必须带「非回答」标签 —— 中间结论不能被当成答案读
    expect(document.querySelector(".chat-reasoning-excerpt-label")).not.toBeNull();
  });

  it("正文已开始时，残留的 reasoningText 绝不渲染", () => {
    // onToken 会清 reasoningText，但渲染层不能依赖那个清理 —— 两道保险各自独立。
    renderBubble({
      m: msg({ content: "「色不異空」出自《心經》。", reasoningText: "殘留的推理" }),
    });
    expect(document.querySelector(".chat-reasoning-excerpt")).toBeNull();
    expect(document.body.textContent).not.toContain("殘留的推理");
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
    // 经名折成简体：界面语言是 zh（见 src/test/setup.ts），而 title_zh 恒为 CBETA 繁体。
    const chip = screen.getByText("《杂阿含经》· 第 16 卷");
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
    expect(screen.getAllByText("《心经》· 第 1 卷")).toHaveLength(1);
    expect(screen.getByText("《金刚经》· 第 1 卷")).toBeInTheDocument();
  });

  it("shows no source list when the answer has no retrieved sources", () => {
    renderBubble({ m: msg({ sources: null }) });
    expect(screen.queryByText("参考经文")).toBeNull();
  });

  it("skips sources without a title (nothing to label the chip with)", () => {
    renderBubble({ m: msg({ sources: [src({ title_zh: undefined })] }) });
    expect(screen.queryByText("参考经文")).toBeNull();
  });

  // ——— 繁简：CBETA 的 title_zh 恒为繁体，界面语言说了算 ———
  // 生产实测（简体界面）：答案正文写「色不异空」，紧跟的引文标记却是
  // 【《般若波羅蜜多心經》第1卷】，chip 也是繁体，而点开抽屉标题又变回简体。
  // 同一部经一屏三种字形，直接削弱「这是同一段原文」的可信度。

  it("内联引文标记的经名跟随界面语言，不直出 CBETA 繁体", () => {
    renderBubble({
      m: msg({
        content: "如【《般若波羅蜜多心經》第1卷】所说。",
        sources: [src({ text_id: 9 as TextId, juan_num: 1, chunk_index: 0, title_zh: "般若波羅蜜多心經" })],
      }),
    });
    expect(document.body.textContent).toContain("《般若波罗蜜多心经》第1卷");
    expect(document.body.textContent).not.toContain("《般若波羅蜜多心經》第1卷");
  });

  it("繁體界面：经名保持繁体，不被折成简体", async () => {
    // 这条才真正证明 i18n.language 被接进了 injectCitationLinks / chip。
    // 只测简体是恒真的——injectCitationLinks 的 language 默认就是 "zh"，
    // 组件哪怕一个参数都不传，简体断言照样绿。
    await i18n.changeLanguage("zh-Hant");
    renderBubble({
      m: msg({
        content: "如【《般若波羅蜜多心經》第1卷】所说。",
        sources: [src({ text_id: 9 as TextId, juan_num: 1, chunk_index: 0, title_zh: "般若波羅蜜多心經" })],
      }),
    });
    expect(document.body.textContent).toContain("《般若波羅蜜多心經》第1卷");
    expect(document.body.textContent).not.toContain("《般若波罗蜜多心经》第1卷");
  });

  it("折字只作用于经名，答案正文里被逐字核验过的引文一字不动", () => {
    // 承重。「已逐字核验」这个徽章的全部价值就在于引文与藏经原文逐字相同；
    // 若界面语言能改写引文本身，徽章当场变成假话。
    renderBubble({
      m: msg({
        content: "论云「無學身語業，即意三牟尼」者。【《雜阿含經》第16卷】",
        sources: [src({ text_id: 5 as TextId, juan_num: 16, chunk_index: 0, title_zh: "雜阿含經" })],
      }),
    });
    expect(document.body.textContent).toContain("「無學身語業，即意三牟尼」");
    expect(document.body.textContent).toContain("《杂阿含经》第16卷");
  });

  it("追问建议是原生 button —— span 上挂 onClick，键盘和读屏永远够不到", () => {
    const { onSuggestionClick } = renderBubble({
      m: msg({ content: "答案正文\n[追问] 什么是阿赖耶识" }),
    });
    const chip = screen.getByRole("button", { name: "什么是阿赖耶识" });
    // 断言标签名而不只是 role：span[role=button] 也能被 getByRole 找到，但浏览器
    // 只为真正的可交互元素把 Enter/空格合成成 click。这里守的正是那一点。
    expect(chip.tagName).toBe("BUTTON");
    expect(chip.tabIndex).toBeGreaterThanOrEqual(0);
    fireEvent.click(chip);
    expect(onSuggestionClick).toHaveBeenCalledWith("什么是阿赖耶识");
  });
});
