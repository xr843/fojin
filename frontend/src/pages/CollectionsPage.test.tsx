import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import CollectionsPage from "./CollectionsPage";
import { api, getAlignmentCatalog } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      get: vi.fn(),
    },
    getAlignmentCatalog: vi.fn(),
  };
});

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderPage(entry = "/collections") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/collections" element={<CollectionsPage />} />
            <Route path="/collections/:collectionId" element={<CollectionsPage />} />
          </Routes>
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe("CollectionsPage", () => {
  beforeAll(() => {
    i18n.addResourceBundle("en", "translation", enTranslation, true, true);
  });

  beforeEach(async () => {
    await i18n.changeLanguage("en");
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    vi.mocked(getAlignmentCatalog).mockResolvedValue({ entries: [], total_pairs: 0 });
  });

  it("renders localized collection data and resource category labels", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Text Collections" })).toBeInTheDocument();
    expect(screen.getByText("Avatamsaka Sutra Series")).toBeInTheDocument();
    expect(screen.getByText("Huayan")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Avatamsaka Sutra Series"));

    expect(screen.getByText("Online Reading")).toBeInTheDocument();
  });

  it("filters by localized text and canonical search query", () => {
    renderPage();
    const input = screen.getByPlaceholderText("Search by title, tradition, author...");

    fireEvent.change(input, { target: { value: "Huayan" } });
    expect(screen.getByText("Avatamsaka Sutra Series")).toBeInTheDocument();
    expect(screen.queryByText("Pure Land Sutras")).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: "净土经" } });
    expect(screen.getByText("Pure Land Sutras")).toBeInTheDocument();
    expect(screen.queryByText("Avatamsaka Sutra Series")).not.toBeInTheDocument();
  });

  it("uses canonical Chinese query for the search action", () => {
    renderPage();

    fireEvent.click(screen.getByText("Avatamsaka Sutra Series"));
    fireEvent.click(screen.getByRole("button", { name: /Search FoJin/ }));

    expect(screen.getByTestId("location")).toHaveTextContent("/search?q=%E5%8D%8E%E4%B8%A5%E7%BB%8F");
  });

  it("exposes the collection toggle as a button reporting its expanded state", () => {
    renderPage();

    const toggle = screen.getByRole("button", { name: /Avatamsaka Sutra Series/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    // The panel the button claims to control must actually exist.
    const panelId = toggle.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();
    expect(document.getElementById(panelId!)).toBeInTheDocument();
  });

  it("renders an indexed text as a real link to its reader page", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { T0278: 4242 } });
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /Avatamsaka Sutra Series/ }));

    // A span with onClick is invisible to keyboards and crawlers; the indexed
    // title must be an anchor carrying a real href.
    const link = await screen.findByRole("link", { name: /大方广佛华严经（六十卷）/ });
    expect(link).toHaveAttribute("href", "/texts/4242");
  });

  it("does not link texts that are not in the corpus", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /Avatamsaka Sutra Series/ }));

    expect(screen.getByText("大方广佛华严经（六十卷）")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /大方广佛华严经（六十卷）/ })).not.toBeInTheDocument();
  });

  it("keeps heading levels contiguous (no h1 -> h3 jump)", () => {
    renderPage();

    expect(screen.getByRole("heading", { level: 1, name: "Text Collections" })).toBeInTheDocument();
    // Each collection is a section of the page, so it sits one level under the h1.
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThan(0);
    expect(screen.queryAllByRole("heading", { level: 3 })).toHaveLength(0);

    // Expanding reveals sub-sections one level down from the card, not two.
    fireEvent.click(screen.getByRole("button", { name: /Avatamsaka Sutra Series/ }));
    expect(screen.getAllByRole("heading", { level: 3 }).length).toBeGreaterThan(0);
    expect(screen.queryAllByRole("heading", { level: 4 })).toHaveLength(0);
  });

  describe("deep linking", () => {
    // A collection used to be reachable only by expanding a local useState, so
    // all 13 shared one URL: unshareable, unbookmarkable, and indistinguishable
    // to crawlers.
    it("opens the collection named in the URL", () => {
      renderPage("/collections/huayan");

      expect(screen.getByText("Online Reading")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Avatamsaka Sutra Series/ }),
      ).toHaveAttribute("aria-expanded", "true");
    });

    it("leaves every collection closed on the bare index", () => {
      renderPage("/collections");

      expect(screen.queryByText("Online Reading")).not.toBeInTheDocument();
    });

    it("falls back to the index for an unknown collection id", () => {
      renderPage("/collections/does-not-exist");

      expect(screen.getByRole("heading", { level: 1, name: "Text Collections" })).toBeInTheDocument();
      expect(screen.queryByText("Online Reading")).not.toBeInTheDocument();
    });

    it("puts the opened collection in the URL", () => {
      renderPage("/collections");

      fireEvent.click(screen.getByRole("button", { name: /Avatamsaka Sutra Series/ }));
      expect(screen.getByTestId("location")).toHaveTextContent("/collections/huayan");
    });

    it("returns to the index URL when the collection is closed again", () => {
      renderPage("/collections/huayan");

      fireEvent.click(screen.getByRole("button", { name: /Avatamsaka Sutra Series/ }));
      expect(screen.getByTestId("location")).toHaveTextContent("/collections");
      expect(screen.queryByText("Online Reading")).not.toBeInTheDocument();
    });

    it("opens only one collection at a time", () => {
      renderPage("/collections/huayan");

      fireEvent.click(screen.getByRole("button", { name: /Pure Land Sutras/ }));

      expect(screen.getByTestId("location")).toHaveTextContent("/collections/pureland");
      expect(
        screen.getByRole("button", { name: /Avatamsaka Sutra Series/ }),
      ).toHaveAttribute("aria-expanded", "false");
    });
  });
});
