import { describe, it, expect, vi, beforeEach, beforeAll, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import WorkDetailPage from "./WorkDetailPage";
import {
  getWork,
  getWorkWitnesses,
  type WorkDetail,
  type WorkWitnessInfo,
} from "../api/client";

// jsdom 不实现 matchMedia；antd List 内部用到响应式断点。
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

vi.mock("../api/client", () => ({
  getWork: vi.fn(),
  getWorkWitnesses: vi.fn(),
}));

const mockGetWork = vi.mocked(getWork);
const mockGetWorkWitnesses = vi.mocked(getWorkWitnesses);

function work(o: Partial<WorkDetail> = {}): WorkDetail {
  return {
    id: 1,
    slug: "lotus-sutra",
    title_primary: "妙法蓮華經",
    title_sa: "Saddharmapuṇḍarīka",
    title_pi: null,
    sc_root_uid: null,
    toh_number: null,
    category: null,
    note: null,
    created_at: "2026-05-30T00:00:00Z",
    witness_count: 2,
    ...o,
  };
}

function witness(o: Partial<WorkWitnessInfo> = {}): WorkWitnessInfo {
  return {
    text_id: 10,
    cbeta_id: "GRETIL-sdp",
    title: "Saddharmapuṇḍarīka",
    lang: "sa",
    canon: "gretil",
    role: "root",
    confidence: "auto",
    has_content: true,
    ...o,
  };
}

function renderPage(slug = "lotus-sutra") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[`/works/${slug}`]}>
          <Routes>
            <Route path="/works/:slug" element={<WorkDetailPage />} />
            <Route path="/404" element={<div>NOT FOUND</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe("WorkDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    i18n.changeLanguage("zh");
  });

  afterEach(() => {
    i18n.changeLanguage("zh");
  });

  it("渲染作品标题、梵文别名、见证本列表与阅读链接", async () => {
    mockGetWork.mockResolvedValue(work());
    mockGetWorkWitnesses.mockResolvedValue([
      witness({ text_id: 10, lang: "sa", role: "root", has_content: true }),
      witness({
        text_id: 20,
        cbeta_id: "T0262",
        title: "妙法蓮華經",
        lang: "lzh",
        canon: "taisho",
        role: "translation",
        has_content: true,
      }),
    ]);

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText("妙法蓮華經").length).toBeGreaterThan(0),
    );
    // 梵文别名 tag（标题区 + 见证本标题各出现，故用 getAllByText）
    expect(screen.getAllByText(/Saddharmapuṇḍarīka/).length).toBeGreaterThan(0);
    // 底本标记
    expect(screen.getByText("底本")).toBeInTheDocument();
    // 两个版本各有阅读链接，指向阅读器
    const readLinks = screen
      .getAllByRole("link")
      .filter((a) => a.getAttribute("href")?.includes("/read"));
    expect(readLinks.length).toBeGreaterThanOrEqual(2);
    expect(
      readLinks.some((a) => a.getAttribute("href") === "/texts/20/read"),
    ).toBe(true);
  });

  it("作品不存在（getWork 报错）时跳转 404", async () => {
    mockGetWork.mockRejectedValue(new Error("404"));
    mockGetWorkWitnesses.mockResolvedValue([]);

    renderPage("does-not-exist");

    await waitFor(() =>
      expect(screen.getByText("NOT FOUND")).toBeInTheDocument(),
    );
  });

  it("renders work-detail chrome in the active UI language", async () => {
    await i18n.changeLanguage("en");
    mockGetWork.mockResolvedValue(work());
    mockGetWorkWitnesses.mockResolvedValue([
      witness({ text_id: 10, lang: "sa", role: "root", has_content: true }),
      witness({
        text_id: 30,
        cbeta_id: "T0263",
        title: "正法華經",
        lang: "lzh",
        canon: "taisho",
        role: "translation",
        has_content: false,
      }),
    ]);

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText("妙法蓮華經").length).toBeGreaterThan(0),
    );
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Works")).toBeInTheDocument();
    expect(screen.getByText("2 witnesses")).toBeInTheDocument();
    expect(screen.getByText("All versions")).toBeInTheDocument();
    expect(screen.getByText("Root text")).toBeInTheDocument();
    expect(screen.getByText("Sanskrit")).toBeInTheDocument();
    expect(screen.getByText("Chinese")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Read/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Details/ })).toBeInTheDocument();
  });

  it("emits hreflang alternates for every supported UI language", async () => {
    mockGetWork.mockResolvedValue(work());
    mockGetWorkWitnesses.mockResolvedValue([]);

    renderPage();

    await waitFor(() => expect(screen.getAllByText("妙法蓮華經").length).toBeGreaterThan(0));
    await waitFor(() => expect(document.head.querySelectorAll('link[rel="alternate"]').length).toBeGreaterThan(0));

    const alternates = new Map(
      Array.from(document.head.querySelectorAll('link[rel="alternate"]')).map((el) => [
        el.getAttribute("hreflang"),
        el.getAttribute("href"),
      ]),
    );
    expect(alternates.get("x-default")).toBe("https://fojin.app/works/lotus-sutra");
    expect(alternates.get("zh")).toBe("https://fojin.app/works/lotus-sutra");
    expect(alternates.get("en")).toBe("https://fojin.app/works/lotus-sutra?lang=en");
    expect(alternates.get("zh-Hant")).toBe("https://fojin.app/works/lotus-sutra?lang=zh-Hant");
  });
});
