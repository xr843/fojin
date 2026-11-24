import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TibetanZhListPage from "./TibetanZhListPage";
import { getTibetanZhIndex } from "../api/tibetanZh";

vi.mock("../api/tibetanZh", async (orig) => ({
  ...(await orig<typeof import("../api/tibetanZh")>()),
  getTibetanZhIndex: vi.fn(),
}));

const it_ = (id: string, title: string, part: string, cat: string) => ({
  id, title, au: "某作者", part, cat, rv: `${id} 审核情况`, md: null, pdf: null, docx: null,
});

describe("TibetanZhListPage", () => {
  it("按部、部类分组列出编号/书名/作者/审核情况，页顶有 AI 提示与 GitHub 链接", async () => {
    vi.mocked(getTibetanZhIndex).mockResolvedValue({
      repo: "", fetched_at: 0, stale: false,
      items: [it_("S-0109", "修心八颂导引文", "松绷", "修心"), it_("T-2796", "真实光明论", "丹珠尔", "中观部")],
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <HelmetProvider>
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <TibetanZhListPage />
          </MemoryRouter>
        </QueryClientProvider>
      </HelmetProvider>,
    );
    expect(screen.getByText("AI 译稿，未经懂藏文的专家审定，仅供研究参考")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "github.com/xr843/tibetan-canon-zh" })).toBeInTheDocument();

    const headings = await screen.findAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(["丹珠尔1 部", "松绷（文集）1 部"]); // 丹珠尔排在松绷前
    const link = screen.getByRole("link", { name: "《真实光明论》" });
    expect(link).toHaveAttribute("href", "/tibetan-zh/T-2796");
    const row = link.closest("li")!;
    expect(within(row).getByText("T-2796")).toBeInTheDocument();
    expect(within(row).getByText("某作者")).toBeInTheDocument();
    expect(within(row).getByText("T-2796 审核情况")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "中观部" })).toBeInTheDocument();
  });
});
