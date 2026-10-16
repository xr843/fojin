import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createRef } from "react";
import type { ChatSource } from "../api/client";
import type { TextId } from "../types/branded";
import type { ParsedCitation } from "../utils/citationLinks";
import { useChatShortcuts } from "../hooks/useChatShortcuts";
import { InlineCitation, PREVIEW_CLOSE_DELAY_MS, PREVIEW_OPEN_DELAY_MS } from "./CitationPreview";
import { CitationPreviewContext, type CitationPreviewData } from "./citationPreviewContext";

const MARK = "【《金刚般若波罗蜜经》第1卷】";
const QUOTE = "應無所住而生其心";
const PARSED: ParsedCitation = { textId: 235, juanNum: 1, chunkIndex: 3, titleZh: "金刚般若波罗蜜经", quote: QUOTE };
const SOURCE: ChatSource = {
  text_id: 235 as TextId, juan_num: 1, chunk_index: 3,
  chunk_text: "須菩提！於意云何？菩薩莊嚴佛土不？不也，世尊！何以故？莊嚴佛土者，則非莊嚴，是名莊嚴。",
  score: 0.9, title_zh: "金剛般若波羅蜜經",
};

function setHoverCapable(matches: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query === "(hover: hover)" ? matches : false,
    media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

function renderCite(
  data: CitationPreviewData | null,
  parsed: ParsedCitation = PARSED,
  onOpen = vi.fn(),
  label: string = MARK,
) {
  const utils = render(
    <CitationPreviewContext.Provider value={data}>
      <p>
        <InlineCitation parsed={parsed} onOpen={onOpen}>{label}</InlineCitation>
      </p>
    </CitationPreviewContext.Provider>,
  );
  return { ...utils, onOpen, btn: screen.getByRole("button", { name: label }) };
}

/** 真实的指针进入：React 的 onPointerEnter 由 pointerover 驱动，并读 pointerType。 */
function pointerIn(el: Element, pointerType = "mouse") {
  fireEvent.pointerOver(el, { pointerType });
}
function pointerOut(el: Element, pointerType = "mouse") {
  fireEvent.pointerOut(el, { pointerType });
}

const realMatchMedia = window.matchMedia;
let track: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  setHoverCapable(true);
  track = vi.fn();
  (globalThis as unknown as { umami: unknown }).umami = { track };
});
afterEach(() => {
  vi.useRealTimers();
  window.matchMedia = realMatchMedia;
  delete (globalThis as unknown as { umami?: unknown }).umami;
});

describe("InlineCitation label", () => {
  it("拆成三段 span 但 textContent 与原标记一字不差（复制完整性）", () => {
    const { btn } = renderCite(null);
    expect(btn.textContent).toBe(MARK);
    expect(btn.querySelector(".chat-cite-title")!.textContent).toBe("《金刚般若波罗蜜经》");
    const marks = [...btn.querySelectorAll(".chat-cite-mark")].map((s) => s.textContent);
    expect(marks).toEqual(["【", "第1卷】"]);
  });

  it("裸《经名》不拆分", () => {
    const { btn } = renderCite(null, PARSED, vi.fn(), "《金刚般若波罗蜜经》");
    expect(btn.querySelector(".chat-cite-title")).toBeNull();
    expect(btn.textContent).toBe("《金刚般若波罗蜜经》");
  });
});

describe("InlineCitation hover preview", () => {
  it("悬停 300ms 才弹出；已核验的引句显示「已逐字核验」，展示只记一次", () => {
    const { btn } = renderCite({
      sources: [SOURCE],
      checkedQuotes: [{ title: "金剛般若波羅蜜經", juan: 1, quote: QUOTE }],
    });
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(PREVIEW_OPEN_DELAY_MS - 50); });
    expect(screen.queryByRole("dialog")).toBeNull();
    act(() => { vi.advanceTimersByTime(60); });
    const card = screen.getByRole("dialog");
    expect(card.textContent).toContain("《金刚般若波罗蜜经》");
    expect(card.textContent).toContain(QUOTE);
    expect(card.textContent).toContain("已逐字核验");
    // 鼠标在引文与卡片之间来回不重复记展示
    pointerOut(btn);
    pointerIn(card);
    pointerOut(card);
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(1000); });
    expect(track.mock.calls.filter((c) => c[0] === "citation_preview_show")).toEqual([
      ["citation_preview_show", { text_id: 235, checked: 1 }],
    ]);
  });

  it("不在 checked_quotes 里就不显示任何核验状态", () => {
    const { btn } = renderCite({
      sources: [SOURCE],
      checkedQuotes: [{ title: "金剛般若波羅蜜經", juan: 1, quote: "凡所有相皆是虛妄" }],
    });
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(PREVIEW_OPEN_DELAY_MS); });
    const card = screen.getByRole("dialog");
    expect(card.textContent).toContain(QUOTE);
    expect(card.textContent).not.toMatch(/核验|核驗|Verbatim/);
    expect(card.querySelector(".chat-cite-preview-verified")).toBeNull();
  });

  it("流式中 trust_status 未到（checkedQuotes 缺席）也不显示核验状态", () => {
    const { btn } = renderCite({ sources: [SOURCE], checkedQuotes: undefined });
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(PREVIEW_OPEN_DELAY_MS); });
    expect(screen.getByRole("dialog").querySelector(".chat-cite-preview-verified")).toBeNull();
  });

  it("没有引句时显示该卷 chunk 的开头并标明「所引卷片段」", () => {
    const { btn } = renderCite({ sources: [SOURCE], checkedQuotes: [] }, { ...PARSED, quote: undefined });
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(PREVIEW_OPEN_DELAY_MS); });
    const card = screen.getByRole("dialog");
    expect(card.textContent).toContain("所引卷片段");
    expect(card.textContent).toContain("須菩提！於意云何？");
  });

  it("别卷的 chunk 不拿来当片段", () => {
    const { btn } = renderCite(
      { sources: [{ ...SOURCE, juan_num: 2 }], checkedQuotes: [] },
      { ...PARSED, quote: undefined },
    );
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(PREVIEW_OPEN_DELAY_MS); });
    expect(screen.getByRole("dialog").textContent).not.toContain("所引卷片段");
  });

  it("移开即收，但停在卡片上不收", () => {
    const { btn } = renderCite({ sources: [SOURCE], checkedQuotes: [] });
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(PREVIEW_OPEN_DELAY_MS); });
    const card = screen.getByRole("dialog");
    pointerOut(btn);
    pointerIn(card);
    act(() => { vi.advanceTimersByTime(PREVIEW_CLOSE_DELAY_MS * 4); });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    pointerOut(card);
    act(() => { vi.advanceTimersByTime(PREVIEW_CLOSE_DELAY_MS + 10); });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("没停够 300ms 就移开，不弹", () => {
    const { btn } = renderCite({ sources: [SOURCE], checkedQuotes: [] });
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(100); });
    pointerOut(btn);
    act(() => { vi.advanceTimersByTime(1000); });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(track).not.toHaveBeenCalled();
  });

  it("触屏不弹卡片，点击仍直接打开", () => {
    const { btn, onOpen } = renderCite({ sources: [SOURCE], checkedQuotes: [] });
    pointerIn(btn, "touch");
    act(() => { vi.advanceTimersByTime(1000); });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.pointerDown(btn, { pointerType: "touch" });
    fireEvent.focus(btn);
    fireEvent.click(btn);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(onOpen).toHaveBeenCalledWith("inline");
  });

  it("不支持 hover 的设备（hover: none）即便是 mouse 事件也不弹", () => {
    setHoverCapable(false);
    const { btn } = renderCite({ sources: [SOURCE], checkedQuotes: [] });
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(1000); });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("卡片里的「打开原文」= 点击，via preview，并收起卡片", () => {
    const { btn, onOpen } = renderCite({ sources: [SOURCE], checkedQuotes: [] });
    pointerIn(btn);
    act(() => { vi.advanceTimersByTime(PREVIEW_OPEN_DELAY_MS); });
    fireEvent.click(screen.getByRole("button", { name: "打开原文" }));
    expect(onOpen).toHaveBeenCalledWith("preview");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("键盘聚焦弹卡片；鼠标点击带来的聚焦不弹", () => {
    const { btn } = renderCite({ sources: [SOURCE], checkedQuotes: [] });
    fireEvent.pointerDown(btn, { pointerType: "mouse" });
    fireEvent.focus(btn);
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.blur(btn);
    fireEvent.focus(btn); // Tab 进来
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.blur(btn);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("Esc 与「停止生成」快捷键", () => {
  function mountShortcuts(onStop: () => void) {
    return renderHook(() =>
      useChatShortcuts({
        sending: true,
        inputRef: createRef<HTMLTextAreaElement>(),
        onStop,
        onNewChat: () => {},
        lastUserText: null,
        onRecall: () => {},
        onToggleHelp: () => {},
      }),
    );
  }

  it("卡片开着时 Esc 只关卡片、不停止生成；卡片关了 Esc 照旧停止", () => {
    const onStop = vi.fn();
    mountShortcuts(onStop);
    const { btn } = renderCite({ sources: [SOURCE], checkedQuotes: [] });
    fireEvent.focus(btn);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(btn, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(onStop).not.toHaveBeenCalled();
    fireEvent.keyDown(btn, { key: "Escape" });
    expect(onStop).toHaveBeenCalledTimes(1);
  });
});
