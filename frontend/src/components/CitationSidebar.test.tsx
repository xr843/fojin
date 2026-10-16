/** 引文边栏：默认收起 / 入口胶囊按需展开 / × 关闭与记忆 / 内联引文直达原文 / 窄屏 / 跨换 id。 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import type { ChatMessageItem, ChatSource } from "../api/client";
import type { TextId } from "../types/branded";
import type { CitationTarget } from "./CitationDrawer";
import CitationSidebar, { OPEN_KEY, type CitationPanelRequest } from "./CitationSidebar";

vi.mock("./CitationDrawer", () => ({
  default: ({ target, onClose }: { target: CitationTarget; onClose: () => void }) => (
    <div data-testid="drawer">
      {target.titleZh}#{target.juanNum}
      <button type="button" onClick={onClose}>close-drawer</button>
    </div>
  ),
}));

const QUOTE = "色不異空空不異色色即是空空即是色";
const SOURCES: ChatSource[] = [
  {
    text_id: 7 as TextId,
    juan_num: 1,
    chunk_index: 3,
    chunk_text: `觀自在菩薩……${QUOTE}，受想行識。`,
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

function answer(over: Partial<ChatMessageItem> = {}): ChatMessageItem {
  return {
    id: 101,
    role: "assistant",
    content: `经云：「${QUOTE}」【《般若波罗蜜多心经》第1卷】。又见【《金刚般若波罗蜜经》第2卷】。`,
    sources: SOURCES,
    created_at: "2026-10-16T02:00:00.000Z",
    trust_status: {
      state: "verified",
      citation_count: 2,
      source_count: 2,
      citation_mutation_count: 0,
      quote_mutation_count: 0,
      quote_checked_count: 1,
      checked_quotes: [{ title: "般若波罗蜜多心经", juan: 1, quote: QUOTE }],
    },
    ...over,
  };
}

const TARGET: CitationTarget = { textId: 7, juanNum: 1, chunkIndex: 3, titleZh: "般若波罗蜜多心经", quote: QUOTE };

let wide = true;
const track = vi.fn();
const realMatchMedia = window.matchMedia;

beforeEach(() => {
  wide = true;
  track.mockReset();
  try { localStorage.clear(); } catch { /* ignore */ }
  window.matchMedia = ((query: string) =>
    ({
      matches: query.includes("min-width: 1280px") ? wide : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList);
  (globalThis as unknown as { umami: unknown }).umami = { track };
});

afterEach(() => {
  window.matchMedia = realMatchMedia;
  delete (globalThis as unknown as { umami?: unknown }).umami;
});

/** Controlled: target / request come from props (rerender to change them). */
function Harness({ messages, target = null, request = null, onTarget }: {
  messages: ChatMessageItem[];
  target?: CitationTarget | null;
  request?: CitationPanelRequest | null;
  onTarget?: (t: CitationTarget | null) => void;
}) {
  return (
    <MemoryRouter>
      <CitationSidebar
        messages={messages}
        sending={false}
        target={target}
        onTargetChange={(t) => onTarget?.(t)}
        request={request}
        width={480}
        onResizeStart={() => {}}
      />
    </MemoryRouter>
  );
}

/** Stateful like ChatPage: buttons stand in for an inline citation and the entry chip. */
function Live({ messages }: { messages: ChatMessageItem[] }) {
  const [target, setTarget] = useState<CitationTarget | null>(null);
  const [request, setRequest] = useState<CitationPanelRequest | null>(null);
  return (
    <MemoryRouter>
      <button type="button" onClick={() => setTarget(TARGET)}>inline-citation</button>
      <button
        type="button"
        onClick={() => { setTarget(null); setRequest({ key: messages[0].created_at }); }}
      >
        entry-chip
      </button>
      <CitationSidebar
        messages={messages}
        sending={false}
        target={target}
        onTargetChange={setTarget}
        request={request}
        width={480}
        onResizeStart={() => {}}
      />
    </MemoryRouter>
  );
}

const rows = () => Array.from(document.querySelectorAll<HTMLButtonElement>(".chat-cpanel-item"));
const panel = () => document.querySelector(".chat-citation-panel");
const req = (m: ChatMessageItem): CitationPanelRequest => ({ key: m.created_at });

describe("CitationSidebar", () => {
  it("wide screen is collapsed by default — nothing rendered, no rail", () => {
    const { container } = render(<Harness messages={[answer()]} />);
    expect(container.querySelector(".chat-citation-panel")).toBeNull();
    expect(container.querySelector(".chat-citation-divider")).toBeNull();
  });

  it("ignores the old #1344 collapsed key: an old user who had it expanded starts collapsed too", () => {
    localStorage.setItem("fojin-citation-sidebar-collapsed", "0");
    render(<Harness messages={[answer()]} />);
    expect(panel()).toBeNull();
  });

  it("entry chip request opens the list of THAT answer, tracks via chip and remembers open", () => {
    const first = answer({ id: 10, created_at: "2026-10-16T01:00:00.000Z" });
    const second = answer({ id: 20, content: "第二条回答没有出处。", sources: [SOURCES[1]], trust_status: null });
    const { rerender, unmount } = render(<Harness messages={[first, second]} />);
    rerender(<Harness messages={[first, second]} request={req(first)} />);
    expect(rows()).toHaveLength(2);
    expect(rows()[0]).toHaveTextContent("已逐字核验");
    expect(rows()[1]).not.toHaveTextContent("已逐字核验");
    expect(screen.getByText("正在看较早的一条回答")).toBeInTheDocument();
    expect(track).toHaveBeenCalledWith("citation_panel_open", { via: "chip" });
    expect(localStorage.getItem(OPEN_KEY)).toBe("1");
    unmount();

    // remembered: next visit opens on the latest answer without a click
    render(<Harness messages={[first, second]} />);
    expect(panel()).not.toBeNull();
    expect(screen.queryByText("正在看较早的一条回答")).toBeNull();
  });

  it("× closes the whole column, is remembered and tracked", () => {
    localStorage.setItem(OPEN_KEY, "1");
    const { unmount } = render(<Harness messages={[answer()]} />);
    expect(panel()).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "关闭引文面板" }));
    expect(panel()).toBeNull();
    expect(localStorage.getItem(OPEN_KEY)).toBe("0");
    expect(track).toHaveBeenCalledWith("citation_panel_close", { view: "list" });
    unmount();
    render(<Harness messages={[answer()]} />);
    expect(panel()).toBeNull();
  });

  it("inline citation while collapsed opens straight into the passage, back goes to the list, not remembered", async () => {
    render(<Live messages={[answer()]} />);
    expect(panel()).toBeNull();
    fireEvent.click(screen.getByText("inline-citation"));
    expect(await screen.findByTestId("drawer")).toBeInTheDocument();
    expect(track).toHaveBeenCalledWith("citation_panel_open", { via: "inline" });
    fireEvent.click(screen.getByRole("button", { name: /返回引文列表/ }));
    expect(screen.queryByTestId("drawer")).toBeNull();
    expect(rows()).toHaveLength(2);
    expect(localStorage.getItem(OPEN_KEY)).toBeNull();
  });

  it("closing from the passage view (drawer ×) closes the column, not just the passage", async () => {
    render(<Live messages={[answer()]} />);
    fireEvent.click(screen.getByText("inline-citation"));
    fireEvent.click(await screen.findByText("close-drawer"));
    expect(panel()).toBeNull();
    expect(track).toHaveBeenCalledWith("citation_panel_close", { view: "passage" });
  });

  it("entry chip while reading a passage switches back to the list", async () => {
    render(<Live messages={[answer()]} />);
    fireEvent.click(screen.getByText("inline-citation"));
    await screen.findByTestId("drawer");
    fireEvent.click(screen.getByText("entry-chip"));
    expect(screen.queryByTestId("drawer")).toBeNull();
    expect(rows()).toHaveLength(2);
    // already open → not counted as another open
    expect(track.mock.calls.filter((c) => c[0] === "citation_panel_open")).toHaveLength(1);
  });

  it("panel click opens the drawer target and tracks citation_click via panel", () => {
    const onTarget = vi.fn();
    const m = answer();
    const { rerender } = render(<Harness messages={[m]} onTarget={onTarget} />);
    rerender(<Harness messages={[m]} request={req(m)} onTarget={onTarget} />);
    fireEvent.click(rows()[0]);
    expect(track).toHaveBeenCalledWith("citation_click", { text_id: 7, via: "panel" });
    expect(onTarget).toHaveBeenCalledWith(expect.objectContaining({ textId: 7, juanNum: 1, chunkIndex: 3, quote: QUOTE }));
  });

  it("narrow screen: the chip opens the list in the drawer slot, but it is not remembered", () => {
    wide = false;
    const m = answer();
    const { rerender, unmount } = render(<Harness messages={[m]} />);
    expect(panel()).toBeNull();
    rerender(<Harness messages={[m]} request={req(m)} />);
    expect(rows()).toHaveLength(2);
    expect(localStorage.getItem(OPEN_KEY)).toBeNull();
    unmount();
    render(<Harness messages={[m]} />);
    expect(panel()).toBeNull();
  });

  it("survives localStorage throwing", () => {
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    try {
      const m = answer();
      const { rerender } = render(<Harness messages={[m]} />);
      expect(panel()).toBeNull();
      rerender(<Harness messages={[m]} request={req(m)} />);
      expect(rows()).toHaveLength(2);
    } finally {
      get.mockRestore();
      set.mockRestore();
    }
  });

  it("a chip request keeps pointing at its answer when the placeholder id is swapped for the real message_id", () => {
    // 登录用户：流中途 message_id 把占位 id 换成真 id；created_at 不变。
    const older = answer({ id: 50, created_at: "2026-10-16T01:00:00.000Z" });
    const live = answer({ id: 1_760_000_000_001, sources: null, trust_status: null, content: "正在检索经文并生成回答..." });
    const request = req(older);
    const { rerender } = render(<Harness messages={[older, live]} />);
    rerender(<Harness messages={[older, live]} request={request} />);
    expect(screen.getByText("正在看较早的一条回答")).toBeInTheDocument();
    const settled = answer({ id: 4242, content: "新回答没有出处。", sources: null, trust_status: null });
    rerender(<Harness messages={[older, settled]} request={request} />);
    expect(screen.getByText("正在看较早的一条回答")).toBeInTheDocument();
    expect(rows()).toHaveLength(2);
  });

  it("follows an inline click into an earlier answer, and returns to latest when a new answer arrives", () => {
    localStorage.setItem(OPEN_KEY, "1");
    const first = answer({ id: 10, created_at: "2026-10-16T01:00:00.000Z" });
    const second = answer({
      id: 20, content: "第二条回答没有出处。", sources: [SOURCES[1]], trust_status: null,
    });
    const { rerender } = render(<Harness messages={[first, second]} />);
    expect(rows()).toHaveLength(0);

    rerender(<Harness messages={[first, second]} target={TARGET} />);
    rerender(<Harness messages={[first, second]} target={null} />);
    expect(screen.getByText("正在看较早的一条回答")).toBeInTheDocument();
    expect(rows()).toHaveLength(2);

    const third = answer({ id: 30, created_at: "2026-10-16T03:00:00.000Z", content: "第三条。", sources: null, trust_status: null });
    act(() => {
      rerender(<Harness messages={[first, second, third]} />);
    });
    expect(screen.queryByText("正在看较早的一条回答")).toBeNull();
  });
});
