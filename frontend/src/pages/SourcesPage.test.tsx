import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
    distributions: [],
    ...o,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/sources"]}>
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
    expect(alternates.get("zh")).toBe("https://fojin.app/sources");
    expect(alternates.get("en")).toBe("https://fojin.app/sources?lang=en");
    expect(alternates.get("zh-Hant")).toBe("https://fojin.app/sources?lang=zh-Hant");
  });
});
