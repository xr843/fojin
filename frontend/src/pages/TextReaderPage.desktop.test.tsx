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
