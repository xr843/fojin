import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SearchPage from "./SearchPage";
import type { DataSource, SearchResponse, UnifiedSearchResponse } from "../api/client";
import { searchDictionaryGrouped, searchUnified } from "../api/client";

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

// 2026-10-12 用户截图：贴了一段 200 多字的《瑜伽師地論》（夹具取自 T1579 卷38 原文），后端 max_length=200 回 422，
// 页面却显示「搜索服务暂时不可用，请稍后重试」——重试多少次都一样。
const LONG =
  "云何菩薩具多勝解？謂諸菩薩於其八種勝解依處，具足成就淨信為先決定喜樂。" +
  "一者、於三寶功德勝解依處，具足成就淨信為先決定喜樂。謂於佛法僧真實功德具多勝解。" +
  "二者、於佛菩薩威力勝解依處，具足成就淨信為先決定喜樂。謂於如前所說威力具多勝解。" +
  "三者、於真實義勝解依處，具足成就淨信為先決定喜樂。謂於如前所說真實義具多勝解。" +
  "四者、於因勝解依處，具足成就淨信為先決定喜樂。謂於種種如應所攝無顛倒因具多勝解。" +
  "五者、於果勝解依處，具足成就淨信為先決定喜樂。謂於種種如應所攝無顛倒果具多勝解。" +
  "六者、於應得義勝解依處，具足成就淨信為先決定喜樂。";

describe("搜索页 · 超长关键词（贴整段经文）", { timeout: 20000 }, () => {
  beforeEach(() => {
    localStorage.clear();
    installMatchMedia(false);
    vi.mocked(searchUnified).mockClear();
    vi.mocked(searchDictionaryGrouped).mockClear();
  });

  it("发给后端的关键词不超过 200 个字，并说明已截取、给出定位出处入口", async () => {
    expect(Array.from(LONG).length).toBeGreaterThan(200);
    renderPage(`/search?q=${encodeURIComponent(LONG)}`);
    expect(await screen.findByText(/已按句截取/, {}, ASYNC)).toHaveClass("s-long-query");
    const sent = vi.mocked(searchUnified).mock.calls.map((c) => c[0].q);
    expect(sent.length).toBeGreaterThan(0);
    for (const q of sent) {
      expect(Array.from(q).length).toBeLessThanOrEqual(200);
      expect(LONG.startsWith(q)).toBe(true);
    }
    const link = screen.getByRole("link", { name: /定位这段原文的出处/ });
    expect(link.getAttribute("href")).toMatch(/^\/verify\?q=/);
    // 长段落不是词条，不再白查一次辞典
    expect(searchDictionaryGrouped).not.toHaveBeenCalled();
  });

  it("200 字以内照常原样搜索，不出说明条", async () => {
    renderPage(`/search?q=${encodeURIComponent("般若")}`);
    await screen.findByText(/一站式综合检索/, {}, ASYNC);
    const calls = vi.mocked(searchUnified).mock.calls;
    expect(calls[calls.length - 1]?.[0].q).toBe("般若");
    expect(screen.queryByText(/已按句截取/)).not.toBeInTheDocument();
  });
});
