import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SearchPage from "./SearchPage";
import type { DataSource, SearchResponse, UnifiedSearchResponse } from "../api/client";
import { searchCrossLanguage, searchTexts, searchUnified } from "../api/client";

const FACETS = {
  canon: [
    { key: "taisho", count: 12 },
    { key: "xuzang", count: 3 },
  ],
  lang: [{ key: "lzh", count: 15 }],
  dynasty: [{ key: "唐", count: 6 }],
  section: [{ key: "prajna", count: 9 }],
};

vi.mock("../api/client", () => ({
  searchTexts: vi.fn(
    async (): Promise<SearchResponse> => ({ total: 0, page: 1, size: 20, results: [], facets: FACETS }),
  ),
  searchContent: vi.fn(),
  searchDictionary: vi.fn(),
  searchCrossLanguage: vi.fn(async () => ({ total: 0, page: 1, size: 20, results: [] })),
  searchSemantic: vi.fn(),
  searchUnified: vi.fn(
    async (): Promise<UnifiedSearchResponse> => ({ query: "金剛經", sections: {}, errors: {}, facets: FACETS }),
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

/** 把当前 URL 的查询串渲染出来，断言「选中项写进了 URL」。 */
function LocationProbe() {
  const loc = useLocation();
  return <output data-testid="loc">{loc.search}</output>;
}

const Q = "/search?q=%E9%87%91%E5%89%9B%E7%B6%93";

function renderPage(url = Q) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[url]}>
          <SearchPage />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

function urlParams(): URLSearchParams {
  return new URLSearchParams(screen.getByTestId("loc").textContent ?? "");
}

describe("搜索页筛选侧栏 · 手机端结果优先", { timeout: 20000 }, () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(searchUnified).mockClear();
  });

  it("手机（≤768px）默认折叠成「筛选」按钮，分面不占首屏", async () => {
    installMatchMedia(true);
    renderPage();
    const toggle = await screen.findByRole("button", { name: /筛选/ }, ASYNC);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("藏经")).not.toBeInTheDocument();
    expect(screen.queryByText("大正藏", { selector: ".s-filter-name" })).not.toBeInTheDocument();
  });

  it("点按钮展开，勾选写进 URL 并带进请求；收起后已选数仍在按钮上", async () => {
    installMatchMedia(true);
    const user = userEvent.setup();
    renderPage();
    const toggle = await screen.findByRole("button", { name: /筛选/ }, ASYNC);

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(toggle.getAttribute("aria-controls")!)!;
    expect(within(panel).getByText("藏经")).toBeInTheDocument();

    await user.click(within(panel).getByText("大正藏", { selector: ".s-filter-name" }));
    expect(urlParams().get("canon")).toBe("taisho");
    expect(toggle).toHaveTextContent("1");
    await vi.waitFor(() =>
      expect(vi.mocked(searchUnified)).toHaveBeenLastCalledWith(expect.objectContaining({ canon: "taisho", facets: true })),
    );

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveTextContent("1");

    await user.click(toggle);
    const reopened = screen.getByText("大正藏", { selector: ".s-filter-name" }).closest("label")!;
    expect(within(reopened).getByRole("checkbox")).toBeChecked();
  });

  it("桌面（>768px）结构不变：侧栏直接展开，没有折叠按钮", async () => {
    installMatchMedia(false);
    renderPage();
    expect(await screen.findByText("大正藏", { selector: ".s-filter-name" }, ASYNC)).toBeInTheDocument();
    expect(screen.getByText("藏经")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^筛选/ })).not.toBeInTheDocument();
  });
});

describe("搜索页分面 · URL 即状态", { timeout: 20000 }, () => {
  beforeEach(() => {
    localStorage.clear();
    installMatchMedia(false);
    vi.mocked(searchUnified).mockClear();
    vi.mocked(searchTexts).mockClear();
    vi.mocked(searchCrossLanguage).mockClear();
  });

  it("无筛选的默认搜索：请求里不带任何筛选参数（与改动前同一请求，只多要分面计数）", async () => {
    renderPage();
    await screen.findByText("大正藏", { selector: ".s-filter-name" }, ASYNC);
    expect(vi.mocked(searchUnified)).toHaveBeenCalledWith({
      q: "金剛經",
      sources: undefined,
      canon: undefined,
      lang: undefined,
      dynasty: undefined,
      section: undefined,
      facets: true,
    });
  });

  it("分享出去的链接：URL 里的多选直接生效、复选框勾着", async () => {
    renderPage(`${Q}&canon=taisho,xuzang&dynasty=${encodeURIComponent("唐")}&section=prajna&tl=lzh`);
    const taisho = (await screen.findByText("大正藏", { selector: ".s-filter-name" }, ASYNC)).closest("label")!;
    expect(within(taisho).getByRole("checkbox")).toBeChecked();
    const xuzang = screen.getByText("卍续藏", { selector: ".s-filter-name" }).closest("label")!;
    expect(within(xuzang).getByRole("checkbox")).toBeChecked();
    expect(vi.mocked(searchUnified)).toHaveBeenCalledWith(
      expect.objectContaining({ canon: "taisho,xuzang", dynasty: "唐", section: "prajna", lang: "lzh" }),
    );
  });

  it("dynasty 不再是死参数：典籍 Tab 把朝代带给 /search，跨语言匹配也按朝代筛但不按语言筛", async () => {
    renderPage(`${Q}&tab=catalog&dynasty=${encodeURIComponent("唐")}&tl=lzh`);
    await vi.waitFor(() =>
      expect(vi.mocked(searchTexts)).toHaveBeenCalledWith(
        expect.objectContaining({ dynasty: "唐", lang: "lzh", facets: true }),
      ),
    );
    await vi.waitFor(() => expect(vi.mocked(searchCrossLanguage)).toHaveBeenCalled());
    const cross = vi.mocked(searchCrossLanguage).mock.calls[0][0];
    expect(cross.dynasty).toBe("唐");
    expect(cross).not.toHaveProperty("lang");
  });

  it("取消勾选与「清除筛选」都回写 URL；旧链接的 ?lang=pi 被语言分面接管", async () => {
    const user = userEvent.setup();
    renderPage(`${Q}&canon=taisho&lang=pi`);
    // 旧 ?lang=pi 仍当语言筛选
    await vi.waitFor(() =>
      expect(vi.mocked(searchUnified)).toHaveBeenCalledWith(expect.objectContaining({ canon: "taisho", lang: "pi" })),
    );
    await user.click(await screen.findByText("汉文", { selector: ".s-filter-name" }, ASYNC));
    expect(urlParams().get("tl")).toBe("pi,lzh");
    expect(urlParams().get("lang")).toBeNull();

    await user.click(screen.getByRole("button", { name: "清除筛选" }));
    const p = urlParams();
    expect([p.get("canon"), p.get("tl"), p.get("dynasty"), p.get("section")]).toEqual([null, null, null, null]);
    expect(p.get("q")).toBe("金剛經");
  });
});

// 桌面上分面侧栏在 DOM 里排在结果前面：（当时的）国家/地区 + 馆藏两组复选框，键盘用户要按约
// 125 次 Tab 才到第一条结果（2026-10-10 生产实测）。侧栏前放一条「跳到结果」链接，
// 平时视觉隐藏、聚焦时出现；目标是结果区容器，tabIndex=-1 让它能接住焦点。
describe("搜索页 · 跳到结果链接", { timeout: 20000 }, () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("侧栏之前有「跳到结果」链接，href 指向结果区 id，结果区可被程序聚焦", async () => {
    installMatchMedia(false);
    renderPage();
    const sidebarItem = await screen.findByText("大正藏", { selector: ".s-filter-name" }, ASYNC);
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
    await screen.findByText("大正藏", { selector: ".s-filter-name" }, ASYNC);
    const skip = screen.getByRole("link", { name: "跳到搜索结果" });
    skip.focus();
    await user.keyboard("{Enter}");
    expect(document.getElementById(skip.getAttribute("href")!.slice(1))).toHaveFocus();
  });
});
