import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import PersonPage from "./PersonPage";
import { getKGEntity, type KGEntityDetail } from "../api/client";

beforeAll(() => {
  i18n.changeLanguage("zh");
});

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getKGEntity: vi.fn(),
  };
});

const mockGetKGEntity = vi.mocked(getKGEntity);

function entity(o: Partial<KGEntityDetail> = {}): KGEntityDetail {
  return {
    id: 1 as KGEntityDetail["id"],
    entity_type: "person",
    name_zh: "鸠摩罗什",
    name_sa: null,
    name_pi: null,
    name_bo: null,
    name_en: "Kumārajīva",
    description: null,
    properties: null,
    text_id: null,
    external_ids: null,
    relations: [],
    ...o,
  };
}

function renderPage(id = "1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[`/person/${id}`]}>
          <Routes>
            <Route path="/person/:id" element={<PersonPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe("PersonPage", () => {
  it("emits hreflang alternates for every supported UI language", async () => {
    mockGetKGEntity.mockResolvedValue(entity());

    renderPage("1");

    await waitFor(() => expect(screen.getAllByText("鸠摩罗什").length).toBeGreaterThan(0));
    await waitFor(() => expect(document.head.querySelectorAll('link[rel="alternate"]').length).toBeGreaterThan(0));

    const alternates = new Map(
      Array.from(document.head.querySelectorAll('link[rel="alternate"]')).map((el) => [
        el.getAttribute("hreflang"),
        el.getAttribute("href"),
      ]),
    );
    expect(alternates.get("x-default")).toBe("https://fojin.app/person/1");
    expect(alternates.get("zh")).toBe("https://fojin.app/person/1");
    expect(alternates.get("en")).toBe("https://fojin.app/person/1?lang=en");
    expect(alternates.get("zh-Hant")).toBe("https://fojin.app/person/1?lang=zh-Hant");
  });
});
