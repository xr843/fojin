/** 引文边栏：宽屏常驻列表 / 窄屏维持原样 / 埋点 / 收起记忆 / 跨换 id 的选中。 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { ChatMessageItem, ChatSource } from "../api/client";
import type { TextId } from "../types/branded";
import type { CitationTarget } from "./CitationDrawer";
import CitationSidebar from "./CitationSidebar";

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

function Harness({ messages, initialTarget = null, onTarget }: {
  messages: ChatMessageItem[];
  initialTarget?: CitationTarget | null;
  onTarget?: (t: CitationTarget | null) => void;
}) {
  return (
    <MemoryRouter>
      <CitationSidebar
        messages={messages}
        sending={false}
        target={initialTarget}
        onTargetChange={(t) => onTarget?.(t)}
        width={480}
        onResizeStart={() => {}}
      />
    </MemoryRouter>
  );
}

const rows = () => Array.from(document.querySelectorAll<HTMLButtonElement>(".chat-cpanel-item"));

describe("CitationSidebar", () => {
  it("wide screen: lists the latest answer's citations with only the backend-listed one marked checked", () => {
    render(<Harness messages={[answer()]} />);
    const items = rows();
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("已逐字核验");
    expect(items[1]).not.toHaveTextContent("已逐字核验");
    // aggregate trust line, same wording as under the answer
    expect(screen.getByText(/引用已校验/)).toBeInTheDocument();
  });

  it("without checked_quotes no row gets a per-citation mark", () => {
    const m = answer();
    m.trust_status = { ...m.trust_status!, checked_quotes: undefined };
    render(<Harness messages={[m]} />);
    expect(screen.queryByText("已逐字核验")).toBeNull();
    expect(screen.getByText(/已逐字核验 1 条引文/)).toBeInTheDocument();
  });

  it("narrow screen keeps the old behaviour: nothing until a citation is opened", () => {
    wide = false;
    const { container } = render(<Harness messages={[answer()]} />);
    expect(container.querySelector(".chat-citation-panel")).toBeNull();
    expect(container.querySelector(".chat-cpanel-rail")).toBeNull();
  });

  it("panel click opens the drawer target and tracks citation_click via panel", () => {
    const onTarget = vi.fn();
    render(<Harness messages={[answer()]} onTarget={onTarget} />);
    fireEvent.click(rows()[0]);
    expect(track).toHaveBeenCalledWith("citation_click", { text_id: 7, via: "panel" });
    expect(onTarget).toHaveBeenCalledWith(expect.objectContaining({ textId: 7, juanNum: 1, chunkIndex: 3, quote: QUOTE }));
  });

  it("with a target, shows the drawer and a back-to-list entry", async () => {
    const onTarget = vi.fn();
    const target = { textId: 7, juanNum: 1, chunkIndex: 3, titleZh: "般若波罗蜜多心经", quote: QUOTE };
    render(<Harness messages={[answer()]} initialTarget={target} onTarget={onTarget} />);
    expect(await screen.findByTestId("drawer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /返回引文列表/ }));
    expect(onTarget).toHaveBeenCalledWith(null);
  });

  it("collapse is remembered in localStorage and tracked", () => {
    const { container, unmount } = render(<Harness messages={[answer()]} />);
    fireEvent.click(screen.getByRole("button", { name: "收起引文面板" }));
    expect(track).toHaveBeenCalledWith("citation_panel_toggle", { state: "collapsed" });
    expect(container.querySelector(".chat-citation-panel")).toBeNull();
    expect(localStorage.getItem("fojin-citation-sidebar-collapsed")).toBe("1");
    unmount();

    render(<Harness messages={[answer()]} />);
    const rail = screen.getByRole("button", { name: "展开引文面板" });
    expect(rail).toHaveTextContent("2");
    fireEvent.click(rail);
    expect(track).toHaveBeenCalledWith("citation_panel_toggle", { state: "expanded" });
    expect(rows()).toHaveLength(2);
  });

  it("survives localStorage throwing", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    try {
      render(<Harness messages={[answer()]} />);
      expect(rows()).toHaveLength(2);
    } finally {
      spy.mockRestore();
    }
  });

  it("stays on the latest answer when its placeholder id is swapped for the real message_id mid-stream", () => {
    // 登录用户：流中途 message_id 把占位 id 换成真 id，同一时刻 trust_status/sources 落地。
    const older = answer({ id: 50, created_at: "2026-10-16T01:00:00.000Z", content: "旧回答没有引文。", sources: null, trust_status: null });
    const live = answer({ id: 1_760_000_000_001, sources: null, trust_status: null, content: "正在检索经文并生成回答..." });
    const { rerender } = render(<Harness messages={[older, live]} />);
    const settled = answer({ id: 4242 }); // same created_at, new id, sources + trust arrived
    rerender(<Harness messages={[older, settled]} />);
    expect(rows()).toHaveLength(2);
    expect(screen.getAllByText("已逐字核验").length).toBeGreaterThan(0);
  });

  it("follows an inline click into an earlier answer, and returns to latest when a new answer arrives", () => {
    const first = answer({ id: 10, created_at: "2026-10-16T01:00:00.000Z" });
    const second = answer({
      id: 20, content: "第二条回答没有出处。", sources: [SOURCES[1]], trust_status: null,
    });
    const target = { textId: 7, juanNum: 1, chunkIndex: 3, titleZh: "般若波罗蜜多心经", quote: QUOTE };
    const { rerender } = render(<Harness messages={[first, second]} />);
    expect(rows()).toHaveLength(0);

    // inline click on the first answer's citation → drawer; back → list of the FIRST answer
    rerender(<Harness messages={[first, second]} initialTarget={target} />);
    rerender(<Harness messages={[first, second]} initialTarget={null} />);
    expect(screen.getByText("正在看较早的一条回答")).toBeInTheDocument();
    expect(rows()).toHaveLength(2);

    // a new question/answer arrives → back to latest
    const third = answer({ id: 30, created_at: "2026-10-16T03:00:00.000Z", content: "第三条。", sources: null, trust_status: null });
    act(() => {
      rerender(<Harness messages={[first, second, third]} />);
    });
    expect(screen.queryByText("正在看较早的一条回答")).toBeNull();
  });
});
