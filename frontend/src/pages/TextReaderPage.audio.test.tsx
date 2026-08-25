import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
  type JuanContentResponse,
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
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
  if (!window.requestAnimationFrame) {
    window.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 0) as unknown as number) as typeof window.requestAnimationFrame;
  }
});

const TEXT_ID = 69 as TextId;

function content(extra: Partial<JuanContentResponse>): JuanContentResponse {
  return {
    text_id: TEXT_ID, cbeta_id: "T0676", title_zh: "解深密經", juan_num: 1, total_juans: 5,
    content: "如是我聞：一時，薄伽梵住最勝光曜七寶莊嚴。", char_count: 20,
    prev_juan: null, next_juan: 2, canon: "taisho", canon_label: "大正藏",
    ...extra,
  };
}

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
  vi.mocked(getJuanLanguages).mockResolvedValue({
    text_id: TEXT_ID, juan_num: 1, languages: ["lzh"], default_lang: "lzh",
  });
  vi.mocked(getJuanLineAnchors).mockResolvedValue({ text_id: TEXT_ID, juan_num: 1, anchors: [] });
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

// 只有心經有音频，其余 10,531 部每换一卷都无条件打一次 /audio 吃 404
//（2026-08-25 走查实测）。读经接口现在带 has_audio，没有就别问。
describe("阅读器只在本卷真有音频时才请求 /audio", () => {
  it("has_audio 缺省/false：不请求", async () => {
    vi.mocked(getJuanContent).mockResolvedValue(content({}));
    await renderReader();
    // 给 react-query 一个 tick 去调度可能的请求，再断言它没发生
    await new Promise((r) => setTimeout(r, 50));
    expect(getJuanAudio).not.toHaveBeenCalled();
  });

  it("has_audio 为 true：请求本卷音频", async () => {
    vi.mocked(getJuanContent).mockResolvedValue(content({ has_audio: true }));
    await renderReader();
    await waitFor(() => expect(getJuanAudio).toHaveBeenCalledWith(69, 1));
  });
});
