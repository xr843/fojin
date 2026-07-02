import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
    expect(screen.getByText("CBETA ID")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Read online/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Read on CBETA/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Export citation/ })).toBeInTheDocument();
  });
});
