import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import OtherVersions from "./OtherVersions";
import { getWorkByText, type WorkByText, type WorkWitnessInfo } from "../api/client";

// jsdom 不实现 matchMedia，而 antd List 内部用到响应式断点（useBreakpoint）。
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

// mock API client
vi.mock("../api/client", () => ({
  getWorkByText: vi.fn(),
}));

const mockGetWorkByText = vi.mocked(getWorkByText);

function witness(o: Partial<WorkWitnessInfo> = {}): WorkWitnessInfo {
  return {
    text_id: 10,
    cbeta_id: "GRETIL-sdp",
    title: "Saddharmapuṇḍarīka",
    lang: "sa",
    canon: "gretil",
    role: "root",
    confidence: "auto",
    has_content: true,
    ...o,
  };
}

function makeWork(o: Partial<WorkByText> = {}): WorkByText {
  return {
    slug: "lotus-sutra",
    title_primary: "妙法蓮華經",
    title_sa: "Saddharmapuṇḍarīka",
    witness_count: 2,
    witnesses: [],
    ...o,
  };
}

function renderPanel(textId: number) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <OtherVersions textId={textId} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OtherVersions 其他版本面板", () => {
  beforeEach(() => {
    mockGetWorkByText.mockReset();
  });

  it("接口返回 null（404）时不渲染任何内容", async () => {
    mockGetWorkByText.mockResolvedValue(null);
    const { container } = renderPanel(20);
    await waitFor(() => expect(mockGetWorkByText).toHaveBeenCalledWith(20));
    expect(container.querySelector(".ant-card")).toBeNull();
    expect(screen.queryByText(/其他版本/)).toBeNull();
  });

  it("仅有当前文本一个见证本（无兄弟）时不渲染任何内容", async () => {
    mockGetWorkByText.mockResolvedValue(
      makeWork({
        witness_count: 1,
        witnesses: [witness({ text_id: 20, role: "translation" })],
      }),
    );
    const { container } = renderPanel(20);
    await waitFor(() => expect(mockGetWorkByText).toHaveBeenCalledWith(20));
    expect(container.querySelector(".ant-card")).toBeNull();
    expect(screen.queryByText(/其他版本/)).toBeNull();
  });

  it("存在其他见证本时渲染版本列表（标题、阅读链接、语言标签、底本标记）", async () => {
    mockGetWorkByText.mockResolvedValue(
      makeWork({
        witness_count: 2,
        witnesses: [
          witness({
            text_id: 10,
            cbeta_id: "GRETIL-sdp",
            title: "Saddharmapuṇḍarīka",
            lang: "sa",
            canon: "gretil",
            role: "root",
            has_content: true,
          }),
          witness({
            text_id: 20,
            cbeta_id: "T0262",
            title: "妙法蓮華經",
            lang: "lzh",
            canon: "taisho",
            role: "translation",
            has_content: true,
          }),
        ],
      }),
    );

    // 当前文本是 text_id=20，所以只应展示 text_id=10 这个兄弟见证本
    renderPanel(20);

    await waitFor(() =>
      expect(screen.getByText("Saddharmapuṇḍarīka")).toBeInTheDocument(),
    );

    // 标题区显示见证本数量
    expect(screen.getByText(/其他版本 · 2 个见证本/)).toBeInTheDocument();

    // 当前文本（妙法蓮華經, T0262）不应出现在兄弟列表中
    expect(screen.queryByText("妙法蓮華經")).toBeNull();
    expect(screen.queryByText("T0262")).toBeNull();

    // 兄弟见证本链接到阅读页（has_content=true → /read）
    const link = screen.getByText("Saddharmapuṇḍarīka").closest("a");
    expect(link).toHaveAttribute("href", "/texts/10/read");

    // 语言标签映射为中文（sa → 梵文）
    expect(screen.getByText("梵文")).toBeInTheDocument();
    // 藏经标签（gretil → GRETIL）
    expect(screen.getByText("GRETIL")).toBeInTheDocument();
    // CBETA 编号
    expect(screen.getByText("GRETIL-sdp")).toBeInTheDocument();
    // root 角色标记「底本」
    expect(screen.getByText("底本")).toBeInTheDocument();

    // 「查看作品全部版本」链接指向作品详情页 /works/{slug}
    const worksLink = screen.getByText(/查看作品全部 2 个版本/).closest("a");
    expect(worksLink).toHaveAttribute("href", "/works/lotus-sutra");
  });

  it("无内容的见证本链接到详情页而非阅读页", async () => {
    mockGetWorkByText.mockResolvedValue(
      makeWork({
        witness_count: 2,
        witnesses: [
          witness({
            text_id: 30,
            cbeta_id: "T0263",
            title: "正法華經",
            lang: "lzh",
            canon: "taisho",
            role: "translation",
            has_content: false,
          }),
        ],
      }),
    );

    renderPanel(20);

    await waitFor(() =>
      expect(screen.getByText("正法華經")).toBeInTheDocument(),
    );

    const link = screen.getByText("正法華經").closest("a");
    expect(link).toHaveAttribute("href", "/texts/30");
    // 中文语言标签
    expect(screen.getByText("中文")).toBeInTheDocument();
    expect(screen.getByText("大正藏")).toBeInTheDocument();
  });
});
