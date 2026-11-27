import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes } from "react-router";
import TextReaderPage from "./TextReaderPage";
import {
  checkBookmark,
  getJuanAudio,
  getJuanContent,
  getJuanInlineNotes,
  getJuanLanguages,
  getJuanLineAnchors,
  getJuanList,
  getTextDetail,
  type TextDetail,
} from "../api/client";
import type { TextId } from "../types/branded";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getTextDetail: vi.fn(),
    getJuanList: vi.fn(),
    getJuanContent: vi.fn(),
    getJuanLanguages: vi.fn(),
    getJuanLineAnchors: vi.fn(),
    getJuanInlineNotes: vi.fn(),
    getJuanAudio: vi.fn(),
    getJuanApparatus: vi.fn(),
    checkBookmark: vi.fn(),
    searchDictionaryGrouped: vi.fn(),
    sendChatMessageStream: vi.fn(),
  };
});

vi.mock("../api/chatModels", () => ({
  fetchChatModels: vi.fn().mockResolvedValue([]),
}));

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
  // 宽屏：所有媒体查询都不命中
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  if (!window.requestAnimationFrame) {
    window.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 0) as unknown as number) as typeof window.requestAnimationFrame;
  }
});

const TEXT_ID = 69 as TextId;

function detail(extra: Partial<TextDetail> = {}): TextDetail {
  return {
    id: TEXT_ID, taisho_id: "T0676", cbeta_id: "T0676", title_zh: "解深密經",
    title_sa: null, title_bo: null, title_pi: null, translator: "玄奘", dynasty: "唐",
    fascicle_count: 5, category: null, subcategory: null, cbeta_url: null,
    has_content: true, content_char_count: 7574, lang: "lzh", created_at: "2026-01-01T00:00:00Z",
    ...extra,
  };
}

beforeEach(() => {
  vi.mocked(getTextDetail).mockResolvedValue(detail());
  vi.mocked(getJuanList).mockResolvedValue({
    text_id: TEXT_ID, title_zh: "解深密經", total_juans: 5,
    juans: [{ juan_num: 1, char_count: 7574 }, { juan_num: 2, char_count: 7000 }],
  });
  vi.mocked(getJuanContent).mockResolvedValue({
    text_id: TEXT_ID, cbeta_id: "T0676", title_zh: "解深密經", juan_num: 1, total_juans: 5,
    content: "如是我聞：一時，薄伽梵住最勝光曜七寶莊嚴。", char_count: 20,
    prev_juan: null, next_juan: 2, canon: "taisho", canon_label: "大正藏",
  });
  vi.mocked(getJuanLanguages).mockResolvedValue({
    text_id: TEXT_ID, juan_num: 1, languages: ["lzh"], default_lang: "lzh",
  });
  vi.mocked(getJuanLineAnchors).mockResolvedValue({ text_id: TEXT_ID, juan_num: 1, anchors: [] });
  vi.mocked(getJuanInlineNotes).mockResolvedValue({ notes: [] });
  vi.mocked(getJuanAudio).mockRejectedValue(new Error("404"));
  vi.mocked(checkBookmark).mockResolvedValue(false);
});

afterEach(() => {
  vi.clearAllMocks();
  localStorage.removeItem("fojin.reader.aiPanel");
});

async function renderReader() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const r = render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/texts/69/read"]}>
          <Routes>
            <Route path="/texts/:id/read" element={<TextReaderPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
  await screen.findByText(/如是我聞/);
  return r;
}

describe("阅读器桌面端：AI 面板记忆与外链标识", () => {
  // 桌面默认开着 420px 的 AI 面板，每次进阅读页都要重新关一次。关过一次就记住。
  it("上次关掉了 AI 面板：这次进来仍是关的，只留浮动按钮；点开后记为 open", async () => {
    localStorage.setItem("fojin.reader.aiPanel", "closed");
    const { container } = await renderReader();
    expect(container.querySelector(".reader-ai-sidebar")).toBeNull();
    expect(container.querySelector(".reader-ai-fab")).not.toBeNull();

    fireEvent.click(container.querySelector(".reader-ai-fab")!);
    await waitFor(() => expect(container.querySelector(".reader-ai-sidebar")).not.toBeNull());
    expect(localStorage.getItem("fojin.reader.aiPanel")).toBe("open");
  });

  it("没有记忆时桌面默认开着（原有行为不变）", async () => {
    const { container } = await renderReader();
    expect(container.querySelector(".reader-ai-sidebar")).not.toBeNull();
  });

  // 「高丽藏」是 window.open 去东国大学 KABC 的外链，却长得和「跨藏对照」这种面板开关
  // 一模一样。给它外链图标。
  it("高丽藏按钮带外链图标", async () => {
    vi.mocked(getTextDetail).mockResolvedValue(detail({ goryeo_k: "K0154", kabc_url: "https://kabc.dongguk.edu/content/view?dataId=ABC_IT_K0154" }));
    const { container } = await renderReader();
    const btn = await screen.findByRole("button", { name: /高丽藏/ });
    expect(btn.querySelector(".anticon-export")).not.toBeNull();
    expect(container.querySelector(".reader-ai-sidebar")).not.toBeNull();
  });
});

// 2026-11-08 真机实测：划一句话时拖出正文右缘再松手，浮层（问小津 / 白话 / 查辞典）不出现——
// mouseup 只挂在正文容器上，松手点在容器外就收不到。
describe("阅读器划选：拖出正文再松手", () => {
  const track = vi.fn();
  beforeAll(() => {
    // jsdom 没实现 Range 的几何方法；浮层定位要用
    const rect = { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) };
    Range.prototype.getBoundingClientRect = () => rect as DOMRect;
    Range.prototype.getClientRects = () => [] as unknown as DOMRectList;
  });
  beforeEach(() => {
    track.mockReset();
    (globalThis as unknown as { umami: { track: typeof track } }).umami = { track };
  });
  afterEach(() => {
    delete (globalThis as unknown as { umami?: unknown }).umami;
    window.getSelection()?.removeAllRanges();
  });

  function selectInBody(text: string) {
    const node = [...document.querySelectorAll("*")]
      .flatMap((el) => [...el.childNodes])
      .find((n) => n.nodeType === Node.TEXT_NODE && n.textContent?.includes(text)) as Text;
    const start = node.textContent!.indexOf(text);
    const range = document.createRange();
    range.setStart(node, start);
    range.setEnd(node, start + text.length);
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
  }

  it("选区在正文里、松手在正文外：浮层照样出现，同一段只记一次 reader_select", async () => {
    await renderReader();
    selectInBody("如是我聞：一時，薄伽梵住最勝光曜七寶莊嚴。"); // 21 字 > MAX_WORD_LEN(20)，算整句
    fireEvent.mouseUp(document.body);
    await waitFor(() => expect(document.querySelector(".reader-dict-popover")).not.toBeNull());
    fireEvent.mouseUp(document.body);
    expect(track.mock.calls.filter(([n]) => n === "reader_select")).toHaveLength(1);
    expect(track).toHaveBeenCalledWith("reader_select", { id: 69, kind: "passage" });
  });

  it("选区不在正文里（比如页面别处的文字）：不弹浮层", async () => {
    await renderReader();
    const outside = document.createElement("p");
    outside.textContent = "页面别处的一段说明文字";
    document.body.appendChild(outside);
    selectInBody("页面别处的一段说明文字");
    fireEvent.mouseUp(document.body);
    await new Promise((r) => setTimeout(r, 50));
    expect(document.querySelector(".reader-dict-popover")).toBeNull();
    outside.remove();
  });
});

// 2026-11-22 用户反馈：从 fojin.ai 核对结果点进来，要高亮「所查的那一整句」，而且一直亮着——
// 之前只闪 CBETA 的一整行 4 秒，还会把同一行里不属于这句的「如是我聞：」也亮了。
// 链接带 ?hl=<起>-<止>（正文偏移，后端核对时算出），阅读器在这两处插零宽标记，标记之间常亮。
describe("阅读器：?hl= 高亮所查的整句", () => {
  async function renderAt(url: string) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const r = render(
      <HelmetProvider>
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={[url]}>
            <Routes>
              <Route path="/texts/:id/read" element={<TextReaderPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </HelmetProvider>,
    );
    await screen.findByText(/如是我聞/);
    return r;
  }

  function between(container: HTMLElement) {
    const start = container.querySelector(".quote-mark[data-q='start']");
    const end = container.querySelector(".quote-mark[data-q='end']");
    if (!start || !end) return null;
    const range = document.createRange();
    range.setStartAfter(start);
    range.setEndBefore(end);
    return range.toString();
  }

  it("标记圈住的正好是所查的那一段，不含同一行前面的字", async () => {
    vi.mocked(getJuanLineAnchors).mockResolvedValue({
      text_id: TEXT_ID, juan_num: 1, anchors: [{ char_offset: 0, line_ref: "0688c05" }],
    });
    const { container } = await renderAt("/texts/69/read?juan=1&anchor=p0688c05&hl=5-10");
    await waitFor(() => expect(between(container)).toBe("一時，薄伽梵"));
  });

  it("没有行号数据时也能圈出来", async () => {
    const { container } = await renderAt("/texts/69/read?juan=1&hl=5-10");
    await waitFor(() => expect(between(container)).toBe("一時，薄伽梵"));
  });

  it("不合法的 hl 不插标记", async () => {
    for (const bad of ["10-5", "abc", "5-99999", "-1-3"]) {
      const { container, unmount } = await renderAt(`/texts/69/read?juan=1&hl=${bad}`);
      expect(container.querySelector(".quote-mark")).toBeNull();
      unmount();
    }
  });
});

describe("阅读器：?quote= 从问答页原文面板过来", () => {
  async function renderAt(url: string) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const r = render(
      <HelmetProvider>
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={[url]}>
            <Routes>
              <Route path="/texts/:id/read" element={<TextReaderPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </HelmetProvider>,
    );
    await screen.findByText(/如是我聞/);
    return r;
  }
  function between(container: HTMLElement) {
    const start = container.querySelector(".quote-mark[data-q='start']");
    const end = container.querySelector(".quote-mark[data-q='end']");
    if (!start || !end) return null;
    const range = document.createRange();
    range.setStartAfter(start);
    range.setEndBefore(end);
    return range.toString();
  }

  it("用引文本身在整卷里定位，简体引文也能对上繁体原文", async () => {
    const q = encodeURIComponent("一时，薄伽梵住");
    const { container } = await renderAt(`/texts/69/read?juan=1&highlight_chunk=0&quote=${q}`);
    await waitFor(() => expect(between(container)).toBe("一時，薄伽梵住"));
  });

  it("引文止于句末时连句号一起高亮", async () => {
    const q = encodeURIComponent("最勝光曜七寶莊嚴");
    const { container } = await renderAt(`/texts/69/read?juan=1&quote=${q}`);
    await waitFor(() => expect(between(container)).toBe("最勝光曜七寶莊嚴。"));
  });

  it("找不到引文时不插标记（仍按 highlight_chunk 大致定位）", async () => {
    const q = encodeURIComponent("一切都是最好的安排");
    const { container } = await renderAt(`/texts/69/read?juan=1&highlight_chunk=0&quote=${q}`);
    expect(container.querySelector(".quote-mark")).toBeNull();
  });
});

describe("阅读器：夹注（CBETA 双行小注）", () => {
  it("夹注按位置插回、小字括号、每条只画一次；段首的夹注放在该段开头", async () => {
    vi.mocked(getJuanContent).mockResolvedValue({
      text_id: TEXT_ID, cbeta_id: "T0676", title_zh: "解深密經", juan_num: 1, total_juans: 5,
      // 0-7 如是我聞四十卷。 | 10-12 骸骨。 | 15-17 拯濟。（行末有句号，重排不会把几段并成一段）
      content: "如是我聞四十卷。\n\n骸骨。\n\n拯濟。", char_count: 13,
      prev_juan: null, next_juan: 2, canon: "taisho", canon_label: "大正藏",
    });
    vi.mocked(getJuanInlineNotes).mockResolvedValue({
      notes: [
        { char_offset: 7, content: "弘始五年出" },
        { char_offset: 13, content: "上戶皆反" },
        { char_offset: 15, content: "段首注" },
      ],
    });
    const { container } = await renderReader();
    await waitFor(() => expect(container.querySelectorAll(".inline-note")).toHaveLength(3));
    const paras = Array.from(container.querySelectorAll(".reader-content p, p")).map((p) => p.textContent ?? "");
    expect(paras).toContain("如是我聞四十卷（弘始五年出）。");
    expect(paras).toContain("骸骨。（上戶皆反）");
    expect(paras).toContain("（段首注）拯濟。");
  });
});

