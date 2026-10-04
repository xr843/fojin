import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReaderDictPopover } from "./ReaderDictPopover";
import { similarQuery, snippetOf, SIMILAR_QUERY_MAX, type SelectionContext } from "./ReaderSelectionExtras.types";
import type { DictPopoverState } from "./ReaderDictPopover.types";
import { searchContent, submitFeedback, type ContentSearchResponse } from "../api/client";

vi.mock("../api/client", () => ({
  searchContent: vi.fn(),
  submitFeedback: vi.fn(),
}));

const mockSearch = vi.mocked(searchContent);
const mockFeedback = vi.mocked(submitFeedback);

const CTX: SelectionContext = {
  textId: 7,
  juanNum: 1,
  title: "金剛般若波羅蜜經",
  cbetaId: "T0235",
  lineRef: "0748c24",
};

const SELECTED = "應無所住，而生其心";

function hit(textId: number, title: string, juan = 1) {
  return {
    text_id: textId,
    cbeta_id: `X${textId}`,
    title_zh: title,
    translator: null,
    dynasty: "清",
    juan_num: juan,
    lang: "lzh",
    source_code: "cbeta",
    highlight: [`是謂<em>無所住而生其心</em>`],
    score: 1,
    matched_juan_count: 1,
    matched_juans: [],
  };
}

function state(text = SELECTED): DictPopoverState {
  return { visible: true, text, x: 100, y: 100, loading: false, result: null };
}

function renderPopover(o: { text?: string; context?: SelectionContext; loggedIn?: boolean } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const props = {
    onClose: vi.fn(),
    onAsk: vi.fn(),
    context: "context" in o ? o.context : CTX,
    loggedIn: o.loggedIn ?? false,
  };
  const ui = (text: string) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ReaderDictPopover state={state(text)} {...props} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const r = render(ui(o.text ?? SELECTED));
  return { ...props, rerenderText: (t: string) => r.rerender(ui(t)) };
}

beforeEach(() => {
  mockSearch.mockReset();
  mockFeedback.mockReset();
});

describe("similarQuery 全藏出处检索词", () => {
  it("标点与空白规整成单空格作小句分隔（不能删：二元组索引跨不过标点）", () => {
    expect(similarQuery("應無所住，而生其心。")).toBe("應無所住 而生其心");
    expect(similarQuery(" 如是\n我聞：「一時」 ")).toBe("如是 我聞 一時");
  });

  it("截断到上限，防止长句整段丢进全文检索", () => {
    const long = "觀".repeat(SIMILAR_QUERY_MAX + 15);
    expect(similarQuery(long)).toHaveLength(SIMILAR_QUERY_MAX);
  });
});

describe("划词浮层：全藏出处", () => {
  it("没有 context 时不出现「全藏出处」「报错」（其它调用方不受影响）", () => {
    renderPopover({ context: undefined });
    expect(screen.queryByRole("button", { name: "全藏出处" })).toBeNull();
    expect(screen.queryByRole("button", { name: "报错" })).toBeNull();
  });

  it("用去标点的检索词查全文，排除本经，链接到对应卷", async () => {
    mockSearch.mockResolvedValue({
      total: 2706,
      results: [hit(7, "金剛般若波羅蜜經（本经，应排除）"), hit(12448, "金剛經注", 2)],
    } as unknown as ContentSearchResponse);
    renderPopover();
    fireEvent.click(screen.getByRole("button", { name: "全藏出处" }));

    const link = await screen.findByRole("link", { name: /金剛經注/ });
    expect(mockSearch).toHaveBeenCalledWith(expect.objectContaining({ q: "應無所住 而生其心", phrase: true }));
    expect(link.getAttribute("href")).toBe("/texts/12448/read?juan=2");
    expect(screen.queryByText(/本经，应排除/)).toBeNull();
    expect(screen.getByRole("link", { name: /查看全部（2706 部）/ }).getAttribute("href")).toBe(
      `/search?q=${encodeURIComponent("應無所住 而生其心")}`,
    );
  });

  it("只命中本经时提示未找到，而不是空白", async () => {
    mockSearch.mockResolvedValue({ total: 1, results: [hit(7, "本经")] } as unknown as ContentSearchResponse);
    renderPopover();
    fireEvent.click(screen.getByRole("button", { name: "全藏出处" }));
    expect(await screen.findByText("其它经论里没有找到这段文字")).toBeInTheDocument();
  });

  it("单字选区（含标点）不发请求", () => {
    renderPopover({ text: "空。" });
    fireEvent.click(screen.getByRole("button", { name: "全藏出处" }));
    expect(screen.getByText(/再多选几个字/)).toBeInTheDocument();
    expect(mockSearch).not.toHaveBeenCalled();
  });

  it("换一段选区后回到辞典模式", async () => {
    mockSearch.mockResolvedValue({ total: 0, results: [] } as unknown as ContentSearchResponse);
    const { rerenderText } = renderPopover();
    fireEvent.click(screen.getByRole("button", { name: "全藏出处" }));
    await screen.findByText("其它经论里没有找到这段文字");
    rerenderText("般若");
    // 辞典模式的空态出现，且没有为新选区再发一次全藏检索
    expect(screen.getByText("辞典未收录，可问小津")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全藏出处" }).className).not.toContain("is-active");
    expect(mockSearch).toHaveBeenCalledTimes(1);
  });
});

describe("划词浮层：报错", () => {
  it("未登录：提示登录，不显示表单", () => {
    renderPopover({ loggedIn: false });
    fireEvent.click(screen.getByRole("button", { name: "报错" }));
    expect(screen.getByText(/登录后可以提交经文勘误/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交勘误" })).toBeNull();
  });

  it("已登录：提交的反馈带经号、卷、行号、选文与说明", async () => {
    mockFeedback.mockResolvedValue({ id: 1, content: "", status: "pending" });
    renderPopover({ loggedIn: true });
    fireEvent.click(screen.getByRole("button", { name: "报错" }));
    fireEvent.change(screen.getByPlaceholderText(/哪里有误/), { target: { value: "「住」疑作「往」" } });
    fireEvent.click(screen.getByRole("button", { name: "提交勘误" }));

    await waitFor(() => expect(mockFeedback).toHaveBeenCalledTimes(1));
    const content = mockFeedback.mock.calls[0][0].content;
    expect(content).toContain("【经文勘误】金剛般若波羅蜜經（T0235）第1卷 · 0748c24");
    expect(content).toContain(`选文：「${SELECTED}」`);
    expect(content).toContain("说明：「住」疑作「往」");
    expect(content).toContain("/texts/7/read?juan=1");
    expect(await screen.findByText(/已收到，谢谢/)).toBeInTheDocument();
  });

  it("提交失败给出提示，可重试", async () => {
    mockFeedback.mockRejectedValue(new Error("500"));
    renderPopover({ loggedIn: true });
    fireEvent.click(screen.getByRole("button", { name: "报错" }));
    fireEvent.click(screen.getByRole("button", { name: "提交勘误" }));
    expect(await screen.findByText("提交失败，请稍后再试")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提交勘误" })).not.toBeDisabled();
  });
});

describe("snippetOf 出处摘要", () => {
  it("优先取含命中标记的片段，而不是落在卷首题名上的首个片段", () => {
    expect(snippetOf(["四分律卷第二十一 姚秦罽賓三藏", "佛<em>在舍衛國</em>祇樹"])).toBe("佛<em>在舍衛國</em>祇樹");
  });
  it("都没有命中标记时退回首个片段；空数组返回 null", () => {
    expect(snippetOf(["甲", "乙"])).toBe("甲");
    expect(snippetOf([])).toBeNull();
  });
});
