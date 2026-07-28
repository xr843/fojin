import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ReaderParallelPanel from "./ReaderParallelPanel";
import {
  getSentenceParallels,
  getCanonicalParallels,
  getJuanAlignment,
  getWorkByText,
  type SentenceAlignmentResponse,
} from "../api/client";

// jsdom 不实现 matchMedia，而 OtherVersions 内的 antd List 用到 useBreakpoint。
beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = (query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList;
  }
});

// mock API client — the panel + its children (OtherVersions / CanonicalView /
// ChunkView) all pull from here.
vi.mock("../api/client", () => ({
  getSentenceParallels: vi.fn(),
  getCanonicalParallels: vi.fn(),
  getJuanAlignment: vi.fn(),
  getFullParallelContent: vi.fn(),
  getWorkByText: vi.fn(),
}));

const mockSentence = vi.mocked(getSentenceParallels);
const mockCanonical = vi.mocked(getCanonicalParallels);
const mockJuan = vi.mocked(getJuanAlignment);
const mockWork = vi.mocked(getWorkByText);

function sentenceResp(total: number): SentenceAlignmentResponse {
  return {
    text_id: 1,
    juan_num: 5,
    total,
    pairs: Array.from({ length: total }, (_, i) => ({
      side_a: { char_start: i, char_end: i + 1, lang: "lzh", text: "汉文句。" },
      side_b: {
        text_id: 9,
        juan_num: 1,
        char_start: i,
        char_end: i + 1,
        lang: "pi",
        title: "MN 10",
        text: "Pāli.",
      },
      similarity: 0.9,
      align_type: "1-1" as const,
      method: "sentence-bertalign",
      is_verified: false,
    })),
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReaderParallelPanel textId={1} juanNum={5} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ReaderParallelPanel 按句对读 tab", () => {
  beforeEach(() => {
    mockSentence.mockReset();
    mockCanonical.mockReset();
    mockJuan.mockReset();
    mockWork.mockReset();
    mockWork.mockResolvedValue(null);
    mockCanonical.mockResolvedValue({
      text_id: 1,
      source_cbeta_id: "T0001",
      source_title: "測試經",
      total: 0,
      parallels: [],
    });
    mockJuan.mockResolvedValue({
      text_id: 1,
      juan_num: 5,
      total_chunks: 0,
      chunks_with_parallels: 0,
      entries: [],
    });
  });

  it("shows 按句对读 tab when sentence data exists", async () => {
    mockSentence.mockResolvedValue(sentenceResp(3));
    renderPanel();
    expect(await screen.findByText(/按句对读|By sentence/)).toBeInTheDocument();
  });

  it("hides 按句对读 tab when sentence data is empty", async () => {
    mockSentence.mockResolvedValue(sentenceResp(0));
    renderPanel();
    // 面板已渲染（按经对读 tab 始终在），且句级查询已完成
    expect(await screen.findByText(/按经对读|By text/)).toBeInTheDocument();
    await waitFor(() => expect(mockSentence).toHaveBeenCalledWith(1, 5));
    expect(screen.queryByText(/按句对读|By sentence/)).not.toBeInTheDocument();
  });
});
