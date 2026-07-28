import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CitationDrawer, { type CitationTarget } from "./CitationDrawer";
import {
  getChunkContext,
  getChunkAlignment,
  type ChunkContextItem,
} from "../api/client";

// jsdom 不实现 matchMedia / scrollIntoView，而 antd Tabs 与 CitationBlocks 用到它们。
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
  Element.prototype.scrollIntoView = vi.fn();
});

vi.mock("../api/client", () => ({
  getChunkContext: vi.fn(),
  getChunkAlignment: vi.fn(),
}));

const mockContext = vi.mocked(getChunkContext);
const mockAlignment = vi.mocked(getChunkAlignment);

const TARGET: CitationTarget = {
  textId: 1558,
  juanNum: 16,
  chunkIndex: 7,
  titleZh: "阿毘達磨俱舍論",
};

function chunk(i: number, text: string, isCenter = false): ChunkContextItem {
  return { chunk_index: i, chunk_text: text, is_center: isCenter };
}

function renderDrawer() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CitationDrawer target={TARGET} onClose={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAlignment.mockResolvedValue({ parallels: [] } as never);
});

describe("CitationDrawer", () => {
  it("引文段落缺失时给出明确空态，而不是把边界提示画在空白正文上", async () => {
    // 线上实际遇到的响应形状：请求的 chunk 不存在，后端返回 200 + 空 chunks。
    // 修复前 has_more_before 由 `low > 0` 算术得出、恒为 true，抽屉于是渲染出
    //「… 前文（本卷第 0 段之前）」——那个 0 是 chunks[0]?.chunk_index ?? 0 的兜底值——
    // 正文却一个字也没有，等于告诉读者「内容就在视野外」，而实际上什么都没找到。
    mockContext.mockResolvedValue({
      text_id: 1558,
      juan_num: 16,
      title_zh: "阿毘達磨俱舍論",
      center_chunk_index: 7,
      radius: 2,
      chunks: [],
      has_more_before: true,
      has_more_after: false,
    } as never);

    renderDrawer();

    await waitFor(() => {
      expect(screen.getByText("本卷未找到该段原文")).toBeInTheDocument();
    });
    expect(screen.queryByText(/前文（本卷第/)).not.toBeInTheDocument();
    expect(screen.queryByText(/第 0 段/)).not.toBeInTheDocument();
  });

  it("正常返回时渲染正文，并按实际 chunk_index 标注前后文", async () => {
    mockContext.mockResolvedValue({
      text_id: 1558,
      juan_num: 16,
      title_zh: "阿毘達磨俱舍論",
      center_chunk_index: 7,
      radius: 2,
      chunks: [chunk(5, "無學身語業，"), chunk(6, "即意三牟尼，", true), chunk(7, "三清淨應知。")],
      has_more_before: true,
      has_more_after: true,
    } as never);

    renderDrawer();

    await waitFor(() => {
      expect(screen.getByText(/即意三牟尼/)).toBeInTheDocument();
    });
    // 边界提示的段号必须来自真实 chunk，不能是兜底的 0
    expect(screen.getByText(/本卷第 5 段之前/)).toBeInTheDocument();
    expect(screen.getByText(/本卷第 7 段之后/)).toBeInTheDocument();
    expect(screen.queryByText("本卷未找到该段原文")).not.toBeInTheDocument();
  });

  it("处于卷首卷末时不显示前后文提示", async () => {
    mockContext.mockResolvedValue({
      text_id: 1558,
      juan_num: 16,
      title_zh: "阿毘達磨俱舍論",
      center_chunk_index: 0,
      radius: 2,
      chunks: [chunk(0, "如是我聞。", true)],
      has_more_before: false,
      has_more_after: false,
    } as never);

    renderDrawer();

    await waitFor(() => {
      expect(screen.getByText(/如是我聞/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/前文（本卷第/)).not.toBeInTheDocument();
    expect(screen.queryByText(/后文（本卷第/)).not.toBeInTheDocument();
  });
});
