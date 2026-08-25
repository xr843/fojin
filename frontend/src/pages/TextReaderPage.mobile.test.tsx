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
} from "../api/client";
import type { TextId } from "../types/branded";

// 阅读页首屏要打的接口全部换成桩；没换的（书签写入、辞典、校勘、流式问答）在
// 本文件的用例里不会被触发。
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

const NARROW_QUERY = "(max-width: 1024px)";

/** 只对阅读器自己的断点查询回答 narrow；antd 的 useBreakpoint 查询一律 false。 */
function installMatchMedia(narrow: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: narrow && query === NARROW_QUERY,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
  if (!window.requestAnimationFrame) {
    window.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 0) as unknown as number) as typeof window.requestAnimationFrame;
  }
});

const TEXT_ID = 69 as TextId;

beforeEach(() => {
  vi.mocked(getTextDetail).mockResolvedValue({
    id: TEXT_ID, taisho_id: "T0676", cbeta_id: "T0676", title_zh: "解深密經",
    title_sa: null, title_bo: null, title_pi: null, translator: "玄奘", dynasty: "唐",
    fascicle_count: 5, category: null, subcategory: null, cbeta_url: null,
    has_content: true, content_char_count: 7574, lang: "lzh", created_at: "2026-01-01T00:00:00Z",
  });
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
  // 只有心經有音频，其余卷后端 404 —— 调用方必须容忍。
  vi.mocked(getJuanAudio).mockRejectedValue(new Error("404"));
  vi.mocked(checkBookmark).mockResolvedValue(false);
});

afterEach(() => {
  vi.clearAllMocks();
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

describe("阅读器 AI 面板在窄屏上的形态", () => {
  // 2026-08-25 Playwright 390px 实测：aiPanelOpen 初值 true，≤1024px 时
  // .reader-with-sidebar.reader-ai-active 锁高 calc(100vh - 64px) + overflow hidden，
  // 列布局里侧栏吃掉 60vh，.reader-container 只剩 178px 且全被标题/导航占掉 ——
  // 经文一行都不露，用户必须先发现并关掉 AI 面板才能读。
  it("窄屏首屏：不内联侧栏、不锁高，经文可见，AI 只留一个浮动按钮", async () => {
    installMatchMedia(true);
    const { container } = await renderReader();

    expect(container.querySelector(".reader-ai-sidebar")).toBeNull();
    expect(container.querySelector(".reader-with-sidebar")!.classList.contains("reader-ai-active")).toBe(false);
    expect(container.querySelector(".reader-ai-fab")).not.toBeNull();
  });

  it("窄屏点浮动按钮：AI 面板以底部抽屉打开，仍不内联", async () => {
    installMatchMedia(true);
    const { container } = await renderReader();

    fireEvent.click(container.querySelector(".reader-ai-fab")!);

    await waitFor(() => {
      expect(document.querySelector(".ant-drawer-open")).not.toBeNull();
    });
    expect(document.querySelector(".ant-drawer-open")!.textContent).toContain("AI 解读");
    expect(container.querySelector(".reader-ai-sidebar")).toBeNull();
  });

  it("宽屏不受影响：AI 面板默认内联打开", async () => {
    installMatchMedia(false);
    const { container } = await renderReader();

    expect(container.querySelector(".reader-ai-sidebar")).not.toBeNull();
    expect(container.querySelector(".reader-with-sidebar")!.classList.contains("reader-ai-active")).toBe(true);
    expect(document.querySelector(".ant-drawer-open")).toBeNull();
  });
});
