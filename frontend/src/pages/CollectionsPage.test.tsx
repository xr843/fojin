import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, useLocation } from "react-router-dom";
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

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/collections"]}>
          <CollectionsPage />
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
});
