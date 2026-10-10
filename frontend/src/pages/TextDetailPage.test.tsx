import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes } from "react-router";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import TextDetailPage from "./TextDetailPage";
import { getTextDetail, type TextDetail } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getTextDetail: vi.fn(),
  };
});

vi.mock("../utils/readingHistory", () => ({
  getLastPosition: vi.fn(() => null),
}));

vi.mock("../utils/history", () => ({
  addViewHistory: vi.fn(),
}));

vi.mock("../components/BookmarkButton", () => ({
  default: () => <button type="button">Bookmark</button>,
}));

vi.mock("../components/RelatedTexts", () => ({
  RelatedTextsStandalone: () => <div data-testid="related-texts" />,
}));

vi.mock("../components/OtherVersions", () => ({
  default: () => <div data-testid="other-versions" />,
}));

vi.mock("../components/CrossCanonEntry", () => ({
  default: () => <div data-testid="cross-canon" />,
}));

vi.mock("../components/SameTitleTexts", () => ({
  default: () => <div data-testid="same-title" />,
}));

vi.mock("../components/CitationGenerator", () => ({
  default: () => <div data-testid="citation-generator" />,
}));

function textDetail(o: Partial<TextDetail> = {}): TextDetail {
  return {
    id: 1 as TextDetail["id"],
    taisho_id: "T0251",
    cbeta_id: "T0251",
    title_zh: "般若波罗蜜多心经",
    title_sa: "Prajñāpāramitāhṛdaya",
    title_bo: null,
    title_pi: null,
    translator: "玄奘",
    dynasty: "唐",
    fascicle_count: 1,
    category: "般若部",
    subcategory: "大正藏",
    cbeta_url: "https://cbetaonline.dila.edu.tw/zh/T0251",
    has_content: true,
    content_char_count: 260,
    lang: "lzh",
    created_at: "2026-01-01T00:00:00Z",
    ...o,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/texts/1"]}>
          <Routes>
            <Route path="/texts/:id" element={<TextDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

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
  i18n.addResourceBundle("en", "translation", enTranslation, true, true);
});

describe("TextDetailPage", () => {
  beforeEach(async () => {
    vi.mocked(getTextDetail).mockResolvedValue(textDetail());
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("zh");
  });

  it("renders text-detail chrome in the active UI language", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("般若波罗蜜多心经")).toBeInTheDocument());
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Search")).toBeInTheDocument();
    expect(screen.getByText("Text details")).toBeInTheDocument();
    expect(screen.getByText("Translator")).toBeInTheDocument();
    expect(screen.getByText("Dynasty")).toBeInTheDocument();
    expect(screen.getByText("Fascicles")).toBeInTheDocument();
    expect(screen.getByText("Collection")).toBeInTheDocument();
    expect(screen.getByText("Sanskrit title")).toBeInTheDocument();
    // 经号只以标签出现（不在表里再写一遍），标签的 title 说明它是什么。
    expect(screen.getByTitle("CBETA ID")).toHaveTextContent("T0251");
    expect(screen.getByRole("button", { name: /Read online/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Read on CBETA/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Export citation/ })).toBeInTheDocument();
  });

  it("emits hreflang alternates for every supported UI language", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("般若波罗蜜多心经")).toBeInTheDocument());
    await waitFor(() => expect(document.head.querySelectorAll('link[rel="alternate"]').length).toBeGreaterThan(0));

    const alternates = new Map(
      Array.from(document.head.querySelectorAll('link[rel="alternate"]')).map((el) => [
        el.getAttribute("hreflang"),
        el.getAttribute("href"),
      ]),
    );
    expect(alternates.get("x-default")).toBe("https://fojin.app/texts/1");
    expect(alternates.get("zh")).toBe("https://fojin.app/texts/1");
    expect(alternates.get("en")).toBe("https://fojin.app/texts/1?lang=en");
    expect(alternates.get("zh-Hant")).toBe("https://fojin.app/texts/1?lang=zh-Hant");
  });

  // 生产 /texts/7 的真实形态：CBETA 译者字段自带朝代前缀「十六國 鳩摩羅什」，
  // 此时再单列「朝代=十六國」就是重复。
  it("omits the dynasty row when the translator already starts with it", async () => {
    vi.mocked(getTextDetail).mockResolvedValue(
      textDetail({ title_zh: "金剛般若波羅蜜經", translator: "十六國 鳩摩羅什", dynasty: "十六國" }),
    );
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("金剛般若波羅蜜經")).toBeInTheDocument());
    const terms = Array.from(container.querySelectorAll(".td-meta dt")).map((el) => el.textContent);
    expect(terms).not.toContain("Dynasty");
    expect(Array.from(container.querySelectorAll(".td-meta dd")).map((el) => el.textContent)).toContain("十六國 鳩摩羅什");
  });

  // 生产 /texts/7：「典藏=大正藏」「CBETA 编号=T0235」与上方两枚标签逐字重复，
  // 「译者=十六國 鳩摩羅什」又把朝代行重复了一遍。
  it("does not repeat in the metadata list what the tags already say", async () => {
    vi.mocked(getTextDetail).mockResolvedValue(
      textDetail({
        cbeta_id: "T0235",
        taisho_id: "T0235",
        title_zh: "金剛般若波羅蜜經",
        title_sa: null,
        translator: "鳩摩羅什",
        dynasty: "十六國",
        category: "大正藏",
        subcategory: "大正藏",
      }),
    );
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("金剛般若波羅蜜經")).toBeInTheDocument());

    const terms = Array.from(container.querySelectorAll(".td-meta dt")).map((el) => el.textContent);
    expect(terms).toEqual(["Translator", "Dynasty", "Fascicles"]);
    const values = Array.from(container.querySelectorAll(".td-meta dd")).map((el) => el.textContent);
    expect(values).toEqual(["鳩摩羅什", "十六國", "1 fascicle"]);
    expect(screen.getByText("T0235")).toBeInTheDocument();
    expect(screen.getByText("大正藏")).toBeInTheDocument();
  });

  it("keeps the collection row when it says something the tag does not", async () => {
    // fixture 默认：标签是分类「般若部」，典藏「大正藏」不同 → 保留
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("般若波罗蜜多心经")).toBeInTheDocument());
    const terms = Array.from(container.querySelectorAll(".td-meta dt")).map((el) => el.textContent);
    expect(terms).toContain("Collection");
    expect(terms).toContain("Sanskrit title");
  });

  it("does not repeat a foreign-language title that is already the heading", async () => {
    vi.mocked(getTextDetail).mockResolvedValue(
      textDetail({
        title_zh: "Vajracchedika Prajnaparamita",
        title_sa: "Vajracchedika Prajnaparamita",
        cbeta_id: "GRETIL-bsu051_u",
        taisho_id: null,
        translator: null,
        dynasty: null,
        category: null,
        subcategory: null,
        cbeta_url: null,
        lang: "sa",
      }),
    );
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("Vajracchedika Prajnaparamita")).toBeInTheDocument());
    const terms = Array.from(container.querySelectorAll(".td-meta dt")).map((el) => el.textContent);
    expect(terms).not.toContain("Sanskrit title");
  });

  it("never paints the id/canon tags in antd's default blue", async () => {
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("般若波罗蜜多心经")).toBeInTheDocument());
    expect(container.querySelectorAll(".ant-tag").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".ant-tag-blue, .ant-tag-geekblue")).toHaveLength(0);
  });

  // 生产上「在线阅读」与「CBETA 阅读」都是实心朱砂，「导出引用」却是无边框文字按钮。
  it("has exactly one primary action, and it is reading on FoJin", async () => {
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("般若波罗蜜多心经")).toBeInTheDocument());
    const primaries = container.querySelectorAll(".td-actions .ant-btn-primary");
    expect(primaries).toHaveLength(1);
    expect(primaries[0]).toHaveTextContent("Read online");
    expect(container.querySelectorAll(".td-actions .ant-btn-text")).toHaveLength(0);
  });

  it("promotes the CBETA link to the primary action when there is no local text", async () => {
    vi.mocked(getTextDetail).mockResolvedValue(textDetail({ has_content: false }));
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("般若波罗蜜多心经")).toBeInTheDocument());
    const primaries = container.querySelectorAll(".td-actions .ant-btn-primary");
    expect(primaries).toHaveLength(1);
    expect(primaries[0]).toHaveTextContent("Read on CBETA");
  });
});
