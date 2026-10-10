import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SearchPage from "./SearchPage";
import type { DataSource, UnifiedSearchResponse } from "../api/client";

vi.mock("../api/client", () => ({
  searchTexts: vi.fn(),
  searchContent: vi.fn(),
  searchDictionary: vi.fn(),
  searchCrossLanguage: vi.fn(),
  searchSemantic: vi.fn(),
  searchUnified: vi.fn(
    async (): Promise<UnifiedSearchResponse> => ({ query: "金剛經", sections: {}, errors: {} }),
  ),
  searchParallelSentences: vi.fn(),
  getSources: vi.fn(async (): Promise<Partial<DataSource>[]> => [
    // 只有「外部 + 有站内搜索模板」的源会进侧栏（见 SearchPage extSearchable）。
    { code: "sat", name_zh: "SAT 大正藏数据库", name_en: "SAT", access_type: "external", region: "日本", languages: "lzh", base_url: "https://example.org" },
    { code: "bdrc", name_zh: "佛教数字资源中心", name_en: "BDRC", access_type: "external", region: "美国", languages: "bo", base_url: "https://example.org" },
  ]),
  getSearchSuggestions: vi.fn(async () => []),
  searchDictionaryGrouped: vi.fn(async () => ({ results: [], total: 0 })),
  getCbetaRedirect: vi.fn(async () => null),
}));

// 整页渲染（antd Tabs/AutoComplete + react-query）比单组件重得多；在并行全量跑时
// findBy 默认 1s 不够等异步 sources 落地，放宽到 5s（与仓内其它整页测试同一量级）。
const ASYNC = { timeout: 5000 };

/** 只对搜索页的手机断点回答 matches=narrow；其余查询（antd 响应式、主题等）一律宽屏。 */
function installMatchMedia(narrow: boolean) {
  window.matchMedia = vi.fn((q: string) => ({
    matches: narrow && q.includes("max-width: 768px"),
    media: q,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

const originalMatchMedia = window.matchMedia;
afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/search?q=%E9%87%91%E5%89%9B%E7%B6%93"]}>
          <SearchPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe("搜索页筛选侧栏 · 手机端结果优先", { timeout: 20000 }, () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("手机（≤768px）默认折叠成「筛选」按钮，分面不占首屏", async () => {
    installMatchMedia(true);
    renderPage();
    // 先等外部源结果行出现，证明 sources 已到——否则「侧栏没条目」可能只是数据还没来
    expect(await screen.findByText("SAT 大正藏数据库", { selector: ".s-ext-row-name" }, ASYNC)).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /筛选/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/国家\/地区/)).not.toBeInTheDocument();
    expect(screen.queryByText("SAT 大正藏数据库", { selector: ".s-filter-name" })).not.toBeInTheDocument();
  });

  it("点按钮展开，再点收起；已选条件跨折叠保留，按钮显示已选数", async () => {
    installMatchMedia(true);
    const user = userEvent.setup();
    renderPage();
    const toggle = await screen.findByRole("button", { name: /筛选/ }, ASYNC);

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/国家\/地区/)).toBeInTheDocument();
    const panel = document.getElementById(toggle.getAttribute("aria-controls")!)!;
    expect(panel).toBeTruthy();
    const satItem = await within(panel).findByText("SAT 大正藏数据库", { selector: ".s-filter-name" }, ASYNC);

    await user.click(satItem);
    expect(toggle).toHaveTextContent("1");

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/国家\/地区/)).not.toBeInTheDocument();
    expect(toggle).toHaveTextContent("1");

    await user.click(toggle);
    const reopened = screen.getByText("SAT 大正藏数据库", { selector: ".s-filter-name" }).closest("label")!;
    expect(within(reopened).getByRole("checkbox")).toBeChecked();
  });

  it("桌面（>768px）结构不变：侧栏直接展开，没有折叠按钮", async () => {
    installMatchMedia(false);
    renderPage();
    expect(await screen.findByText("SAT 大正藏数据库", { selector: ".s-filter-name" }, ASYNC)).toBeInTheDocument();
    expect(screen.getByText(/国家\/地区/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /筛选/ })).not.toBeInTheDocument();
  });
});

// 桌面上分面侧栏在 DOM 里排在结果前面：国家/地区 + 馆藏两组复选框，键盘用户要按约
// 125 次 Tab 才到第一条结果（2026-10-10 生产实测）。侧栏前放一条「跳到结果」链接，
// 平时视觉隐藏、聚焦时出现；目标是结果区容器，tabIndex=-1 让它能接住焦点。
describe("搜索页 · 跳到结果链接", { timeout: 20000 }, () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("侧栏之前有「跳到结果」链接，href 指向结果区 id，结果区可被程序聚焦", async () => {
    installMatchMedia(false);
    renderPage();
    const sidebarItem = await screen.findByText("SAT 大正藏数据库", { selector: ".s-filter-name" }, ASYNC);
    const skip = screen.getByRole("link", { name: "跳到搜索结果" });
    const href = skip.getAttribute("href")!;
    expect(href).toMatch(/^#.+/);
    const target = document.getElementById(href.slice(1))!;
    expect(target).toBeTruthy();
    expect(target).toHaveClass("s-main");
    expect(target).toHaveAttribute("tabindex", "-1");
    // 必须排在侧栏之前，否则它本身也要 Tab 过整个侧栏才到得了
    expect(skip.compareDocumentPosition(sidebarItem) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(skip.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    target.focus();
    expect(target).toHaveFocus();
  });

  it("键盘：从链接回车后焦点落到结果区", async () => {
    installMatchMedia(false);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("SAT 大正藏数据库", { selector: ".s-filter-name" }, ASYNC);
    const skip = screen.getByRole("link", { name: "跳到搜索结果" });
    skip.focus();
    await user.keyboard("{Enter}");
    expect(document.getElementById(skip.getAttribute("href")!.slice(1))).toHaveFocus();
  });
});
