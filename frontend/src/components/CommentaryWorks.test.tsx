import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CommentaryWorks from "./CommentaryWorks";
import { getCommentaryCorpus, type CommentaryCorpus, type CommentaryCorpusCommentary } from "../api/client";

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

vi.mock("../api/client", () => ({
  getCommentaryCorpus: vi.fn(),
}));

function c(o: Partial<CommentaryCorpusCommentary> = {}): CommentaryCorpusCommentary {
  return {
    cbeta_id: "X0461",
    work: "X24n0461",
    title: "金剛經註",
    tier: "A",
    anchors: 100,
    base_work: "T08n0235",
    base_title: "金剛般若波羅蜜經",
    text_id: 12403,
    ...o,
  };
}

function corpus(commentaries: CommentaryCorpusCommentary[]): CommentaryCorpus {
  return {
    sutras: [
      { base_work: "T08n0235", base_title: "金剛般若波羅蜜經", commentary_count: 52, line_coverage_pct: 90, text_id: 7 },
      { base_work: "T29n1558", base_title: "阿毘達磨俱舍論", commentary_count: 5, line_coverage_pct: 12, text_id: 38 },
    ],
    commentaries,
    caveats: [],
  };
}

function renderPanel(textId: number) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CommentaryWorks textId={textId} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CommentaryWorks 历代注疏", () => {
  beforeEach(() => vi.mocked(getCommentaryCorpus).mockReset());

  it("列出注这部经的注疏：有 fojin 文本的链到详情页，没有的只列题名", async () => {
    vi.mocked(getCommentaryCorpus).mockResolvedValue(
      corpus([
        c(),
        c({ cbeta_id: "B0023", work: "B07n0023", title: "金剛般若波羅蜜經講義", text_id: null }),
        c({ cbeta_id: "T1821", work: "T41n1821", title: "俱舍論記", base_work: "T29n1558", text_id: 7993 }),
      ]),
    );
    renderPanel(7);
    await waitFor(() => expect(screen.getByText("金剛經註")).toBeInTheDocument());
    expect(screen.getByText(/历代注疏/)).toBeInTheDocument();
    expect(screen.getByText("金剛經註").closest("a")).toHaveAttribute("href", "/texts/12403");
    expect(screen.getByText("金剛般若波羅蜜經講義").closest("a")).toBeNull();
    // 别的经的注疏不混进来
    expect(screen.queryByText("俱舍論記")).toBeNull();
    // 覆盖不完整是数据事实，必须写出来
    expect(screen.getByText(/不等于全部注家/)).toBeInTheDocument();
  });

  it("隔离档（quarantine）的注疏不列出", async () => {
    vi.mocked(getCommentaryCorpus).mockResolvedValue(
      corpus([c(), c({ cbeta_id: "X9999", title: "可疑之作", tier: "quarantine", text_id: 1 })]),
    );
    renderPanel(7);
    await waitFor(() => expect(screen.getByText("金剛經註")).toBeInTheDocument());
    expect(screen.queryByText("可疑之作")).toBeNull();
  });

  it("本经不在经注语料里时整块不渲染", async () => {
    vi.mocked(getCommentaryCorpus).mockResolvedValue(corpus([c()]));
    const { container } = renderPanel(36);
    await waitFor(() => expect(getCommentaryCorpus).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("注家多时先收起，展开后显示全部", async () => {
    vi.mocked(getCommentaryCorpus).mockResolvedValue(
      corpus(Array.from({ length: 20 }, (_, i) => c({ cbeta_id: `X${i}`, title: `注疏${i}`, anchors: 100 - i }))),
    );
    renderPanel(7);
    await waitFor(() => expect(screen.getByText("注疏0")).toBeInTheDocument());
    expect(screen.queryByText("注疏19")).toBeNull();
    screen.getByRole("button", { name: /展开全部/ }).click();
    await waitFor(() => expect(screen.getByText("注疏19")).toBeInTheDocument());
  });
});
