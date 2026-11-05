import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import CommentaryExcerpts from "./CommentaryExcerpts";
import { getCommentaryCorpus, getCommentaryExcerpts } from "../api/client";

vi.mock("../api/client", () => ({ getCommentaryCorpus: vi.fn(), getCommentaryExcerpts: vi.fn() }));
const mockCorpus = vi.mocked(getCommentaryCorpus);
const mockEx = vi.mocked(getCommentaryExcerpts);

const KOSA_TEXT_ID = 1558;
const QUOTE = "謂前生唯諸前生與後相似生未生法為同類因";

function corpus(excerpts: boolean) {
  return {
    sutras: [{ base_work: "T29n1558", base_title: "阿毘達磨俱舍論", commentary_count: 5, line_coverage_pct: 12, text_id: KOSA_TEXT_ID, excerpts }],
    commentaries: [],
    caveats: [],
  };
}

function renderIt(textId = KOSA_TEXT_ID) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CommentaryExcerpts textId={textId} quote={QUOTE} />
    </QueryClientProvider>,
  );
}

/** 等语料表真的渲染进组件——只等到「请求发出」会在数据到达前就断言，负向用例恒绿。 */
async function settle() {
  await waitFor(() => expect(mockCorpus).toHaveBeenCalled());
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30));
  });
}

beforeEach(() => {
  mockCorpus.mockReset();
  mockEx.mockReset();
  i18n.changeLanguage("zh");
});

describe("CommentaryExcerpts", () => {
  it("定位到的论没有片段数据时什么都不显示，也不去取片段", async () => {
    mockCorpus.mockResolvedValue(corpus(false));
    const { container } = renderIt();
    await settle();
    expect(container.querySelector('[data-testid="commentary-excerpts"]')).toBeNull();
    expect(mockEx).not.toHaveBeenCalled();
  });

  it("别的书（不在语料里）不显示", async () => {
    mockCorpus.mockResolvedValue(corpus(true));
    const { container } = renderIt(9);
    await settle();
    expect(container.querySelector('[data-testid="commentary-excerpts"]')).toBeNull();
  });

  it("有数据：先只显示按钮，点开才按贴文取片段，给原文与站内阅读链接", async () => {
    mockCorpus.mockResolvedValue(corpus(true));
    mockEx.mockResolvedValue({
      query: QUOTE, matched: true, base_work: "T29n1558", base_title: "阿毘達磨俱舍論", caveats: [],
      excerpts: [{
        work: "T41n1821", title: "俱舍論記", tier: "A",
        text: "「謂前生至為同類因」者，答。正釋前生。", line_from: "0118c23", line_to: "0118c24",
        anchor: "T41n1821_p0118c23", truncated: true, urn: null,
        reader_url: "https://fojin.app/texts/123/read?juan=6#p0118c23",
      }],
    });
    renderIt();
    const btn = await screen.findByTestId("commentary-excerpts-toggle");
    expect(btn).toHaveTextContent("注疏怎么讲这几句");
    expect(mockEx).not.toHaveBeenCalled();

    fireEvent.click(btn);
    expect(await screen.findByText(/正釋前生/)).toBeInTheDocument();
    expect(mockEx).toHaveBeenCalledWith(QUOTE);
    expect(screen.getByText("《俱舍论记》")).toBeInTheDocument(); // 简体界面书名转简体
    const link = screen.getByText("在阅读器打开").closest("a")!;
    expect(link).toHaveAttribute("href", "/texts/123/read?juan=6#p0118c23");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByText("……下文未完")).toBeInTheDocument();
  });

  it("一家都没牒到时如实说明，不留空白", async () => {
    mockCorpus.mockResolvedValue(corpus(true));
    mockEx.mockResolvedValue({ query: QUOTE, matched: true, base_work: "T29n1558", base_title: null, excerpts: [], caveats: [] });
    renderIt();
    fireEvent.click(await screen.findByTestId("commentary-excerpts-toggle"));
    expect(await screen.findByText(/没有逐字牒到这几句/)).toBeInTheDocument();
  });
});
