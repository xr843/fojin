import { describe, it, expect, vi, beforeAll, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import SourcesPage from "./SourcesPage";
import { getSources, type DataSource } from "../api/client";

beforeAll(() => {
  i18n.changeLanguage("zh");
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

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getSources: vi.fn(),
  };
});

const mockGetSources = vi.mocked(getSources);

function source(o: Partial<DataSource> = {}): DataSource {
  return {
    id: 1 as DataSource["id"],
    code: "cbeta",
    name_zh: "CBETA",
    name_en: "CBETA",
    base_url: "https://cbetaonline.dila.edu.tw",
    description: null,
    access_type: "external",
    region: "Taiwan, China",
    languages: "lzh",
    research_fields: null,
    supports_search: true,
    supports_fulltext: true,
    has_local_fulltext: false,
    has_remote_fulltext: true,
    supports_iiif: false,
    supports_api: false,
    sort_order: 0,
    is_active: true,
    health_status: "ok",
    health_checked_at: null,
    health_detail: null,
    health_confidence: "high",
    distributions: [],
    ...o,
  };
}

function renderPage(url = "/sources") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[url]}>
          <SourcesPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe("SourcesPage", () => {
  it("emits hreflang alternates for every supported UI language", async () => {
    mockGetSources.mockResolvedValue([source()]);

    renderPage();

    await waitFor(() => expect(document.head.querySelectorAll('link[rel="alternate"]').length).toBeGreaterThan(0));

    const alternates = new Map(
      Array.from(document.head.querySelectorAll('link[rel="alternate"]')).map((el) => [
        el.getAttribute("hreflang"),
        el.getAttribute("href"),
      ]),
    );
    expect(alternates.get("x-default")).toBe("https://fojin.app/sources");
    expect(alternates.get("zh-Hans")).toBe("https://fojin.app/sources");
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe("https://fojin.app/sources");
    expect(alternates.get("en")).toBe("https://fojin.app/sources?lang=en");
    expect(alternates.get("zh-Hant")).toBe("https://fojin.app/sources?lang=zh-Hant");
  });
});

// ---------------------------------------------------------------------------
// 手机端目录折叠（2026-10-11）：生产 390×844 整页 51,389px ≈ 61 屏。
// 手机上分组默认收起、顶部给分组概览；任何筛选/搜索命中时相关分组自动展开；
// 收起的卡片仍留在 DOM（<details> / CSS 隐藏），不靠「不渲染」来变短。
// ---------------------------------------------------------------------------
const originalMatchMedia = window.matchMedia;

function mockPhone(phone: boolean) {
  window.matchMedia = ((query: string) =>
    ({
      matches: phone && query.includes("max-width"),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList) as typeof window.matchMedia;
}

function catalog(): DataSource[] {
  const tw = Array.from({ length: 15 }, (_, i) =>
    source({ id: (100 + i) as DataSource["id"], code: `tw-${i}`, name_zh: `台湾源${i}`, name_en: `TW ${i}`, region: "中国台湾", sort_order: i }),
  );
  return [
    source({ id: 1 as DataSource["id"], code: "cbeta", name_zh: "CBETA 中華電子佛典協會", region: "中国台湾", sort_order: -100 }),
    ...tw,
    source({ id: 2 as DataSource["id"], code: "suttacentral", name_zh: "SuttaCentral 巴利经藏", name_en: "SuttaCentral", region: "澳大利亚", sort_order: -6 }),
    source({ id: 3 as DataSource["id"], code: "sat", name_zh: "SAT 大正藏数据库", name_en: "SAT", region: "日本" }),
  ];
}

function groupOf(text: string): HTMLDetailsElement {
  const el = screen.getByText(text);
  const details = el.closest("details");
  if (!details) throw new Error(`${text} is not inside a <details> group`);
  return details as HTMLDetailsElement;
}

describe("SourcesPage 手机目录折叠", () => {
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it("手机上分组默认收起，但收起的来源名称仍在 DOM 里（SEO / 页内查找）", async () => {
    mockPhone(true);
    mockGetSources.mockResolvedValue(catalog());
    renderPage();
    await screen.findByText("SuttaCentral 巴利经藏");
    expect(groupOf("SuttaCentral 巴利经藏").open).toBe(false);
    expect(groupOf("CBETA 中華電子佛典協會").open).toBe(false);
    // 超过每组折叠上限（12）的那几条也要在 DOM 里，只是隐藏
    expect(screen.getByText("台湾源14")).toBeTruthy();
  });

  it("桌面保持原样：分组默认展开", async () => {
    mockPhone(false);
    mockGetSources.mockResolvedValue(catalog());
    renderPage();
    await screen.findByText("SuttaCentral 巴利经藏");
    expect(groupOf("SuttaCentral 巴利经藏").open).toBe(true);
  });

  it("顶部分组概览：每组一个入口带数量，点开即展开该组", async () => {
    mockPhone(true);
    mockGetSources.mockResolvedValue(catalog());
    const { container } = renderPage();
    await screen.findByText("SuttaCentral 巴利经藏");
    const overview = container.querySelector(".sources-overview");
    expect(overview).toBeTruthy();
    const chips = Array.from(overview!.querySelectorAll("button"));
    expect(chips.map((b) => b.textContent)).toEqual(["中国台湾16", "日本1", "澳大利亚1"]);
    fireEvent.click(chips[2]);
    expect(groupOf("SuttaCentral 巴利经藏").open).toBe(true);
    expect(groupOf("CBETA 中華電子佛典協會").open).toBe(false);
  });

  it("搜索命中时相关分组自动展开（深链 ?q= 落地也一样）", async () => {
    mockPhone(true);
    mockGetSources.mockResolvedValue(catalog());
    renderPage("/sources?q=SuttaCentral");
    await screen.findByText("SuttaCentral 巴利经藏");
    expect(groupOf("SuttaCentral 巴利经藏").open).toBe(true);
  });

  it("地区筛选深链 ?region= 落地时该组展开", async () => {
    mockPhone(true);
    mockGetSources.mockResolvedValue(catalog());
    renderPage("/sources?region=" + encodeURIComponent("中国台湾"));
    await screen.findByText("CBETA 中華電子佛典協會");
    expect(groupOf("CBETA 中華電子佛典協會").open).toBe(true);
  });

  it("关键词搜索时组内不再截断到 12 条：命中的每一条都可见", async () => {
    mockPhone(true);
    mockGetSources.mockResolvedValue(catalog());
    renderPage("/sources?q=" + encodeURIComponent("台湾源"));
    await screen.findByText("台湾源14");
    const card = screen.getByText("台湾源14").closest(".source-card");
    expect(card?.classList.contains("is-overflow")).toBe(false);
    expect(screen.queryByRole("button", { name: /展开全部/ })).toBeNull();
  });

  it("未搜索时超出 12 条的卡片标为折叠，点「展开全部」后取消", async () => {
    mockPhone(false);
    mockGetSources.mockResolvedValue(catalog());
    renderPage();
    await screen.findByText("台湾源14");
    expect(screen.getByText("台湾源14").closest(".source-card")?.classList.contains("is-overflow")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /展开全部/ }));
    expect(screen.getByText("台湾源14").closest(".source-card")?.classList.contains("is-overflow")).toBe(false);
  });

  it("来源/可信度声明：桌面在目录上方，手机布局才移到目录之后（只渲染一份）", async () => {
    for (const phone of [false, true]) {
      mockPhone(phone);
      mockGetSources.mockResolvedValue(catalog());
      const { container, unmount } = renderPage();
      await screen.findByText("SuttaCentral 巴利经藏");
      const trusts = container.querySelectorAll(".sources-trust");
      expect(trusts.length).toBe(1);
      const groups = container.querySelector(".sources-groups")!;
      const trustBeforeGroups = !!(trusts[0].compareDocumentPosition(groups) & Node.DOCUMENT_POSITION_FOLLOWING);
      expect(trustBeforeGroups).toBe(!phone);
      unmount();
    }
  });
});
