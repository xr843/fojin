import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import ExportsPage from "./ExportsPage";
import api from "../api/client";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
  },
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ExportsPage />
    </QueryClientProvider>,
  );
}

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", enTranslation, true, true);
});

describe("ExportsPage", () => {
  beforeEach(async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        texts: 1234,
        kg_entities: 56,
        kg_relations: 78,
      },
    });
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("zh");
  });

  it("renders export-page chrome in the active UI language", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("Open Data Downloads")).toBeInTheDocument());
    expect(screen.getByText(/FoJin platform data is available under an open license/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Text metadata")).toBeInTheDocument());
    expect(screen.getByText("Knowledge graph entities")).toBeInTheDocument();
    expect(screen.getByText("Knowledge graph relations")).toBeInTheDocument();
    expect(screen.getByText("Buddhist Text Metadata (CSV)")).toBeInTheDocument();
    expect(screen.getByText(/IDs, titles, translators, dynasties, categories/)).toBeInTheDocument();
    expect(screen.getAllByText("Dynasty").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Category").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Entity type").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Download CSV/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download JSON$/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download JSON-LD/ })).toBeInTheDocument();
  });
});
