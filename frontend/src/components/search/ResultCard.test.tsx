import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import ResultCard from "./ResultCard";
import CrossLangCard from "./CrossLangCard";
import type { CrossLanguageSearchHit, SearchHit } from "../../api/client";
import type { TextId } from "../../types/branded";

vi.mock("../../api/client", () => ({
  getAlignmentCatalog: vi.fn(async () => ({ entries: [] })),
}));

function makeHit(overrides: Partial<SearchHit> = {}): SearchHit {
  return {
    id: 236 as TextId,
    taisho_id: "T0235",
    cbeta_id: "T0235",
    title_zh: "金剛般若波羅蜜經",
    translator: "鳩摩羅什",
    dynasty: "十六國",
    category: "大正藏",
    cbeta_url: null,
    has_content: true,
    source_code: "cbeta",
    lang: "lzh",
    score: 1,
    highlight: { title_zh: ["<em>金剛</em>般若波羅蜜經"] },
    related_translations: [],
    ...overrides,
  };
}

function makeCrossHit(overrides: Partial<CrossLanguageSearchHit> = {}): CrossLanguageSearchHit {
  return {
    ...makeHit(),
    title_en: "Diamond Sutra",
    title_sa: null,
    title_pi: null,
    title_bo: null,
    lang: "lzh",
    ...overrides,
  } as CrossLanguageSearchHit;
}

function renderWithProviders(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// 经名本身就是去详情页的主链接：此前标题是死文字，唯一入口是每张卡上一颗实心朱砂
// 「查看详情」——一页十几颗主按钮，视觉重心全压在按钮上，而经名反倒点不动。
describe.each([
  ["ResultCard", () => renderWithProviders(<ResultCard hit={makeHit()} />)],
  ["CrossLangCard", () => renderWithProviders(<CrossLangCard hit={makeCrossHit()} />)],
])("%s 经名即主链接", (_name, renderIt) => {
  it("经名是指向 /texts/{id} 的链接，且保留命中高亮", () => {
    const { container } = renderIt();
    const link = screen.getByRole("link", { name: "金剛般若波羅蜜經" });
    expect(link).toHaveAttribute("href", "/texts/236");
    expect(link.querySelector("em")?.textContent).toBe("金剛");
    expect(container.querySelector(".s-card-title a")).toBe(link);
  });

  it("不再有实心「查看详情」主按钮", () => {
    const { container } = renderIt();
    expect(screen.queryByText("查看详情")).not.toBeInTheDocument();
    expect(container.querySelector(".ant-btn-primary")).toBeNull();
  });

  it("不渲染「排序 #N」窄栏——顺序本身就是排序", () => {
    const { container } = renderIt();
    expect(container.querySelector(".s-card-rank")).toBeNull();
    expect(screen.queryByText(/排序/)).not.toBeInTheDocument();
  });
});
