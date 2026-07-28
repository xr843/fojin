import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import zhHantTranslation from "../../public/locales/zh-Hant/translation.json";
import CrossCanonPage from "./CrossCanonPage";
import { getAlignmentCatalog } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, getAlignmentCatalog: vi.fn() };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/cross-canon"]}>
        <CrossCanonPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CrossCanonPage", () => {
  beforeAll(() => {
    // Only `zh` is inlined; other bundles load over HttpBackend, which never
    // resolves under jsdom.
    i18n.addResourceBundle("zh-Hant", "translation", zhHantTranslation, true, true);
  });

  beforeEach(() => {
    // CBETA's own title string — always traditional.
    vi.mocked(getAlignmentCatalog).mockResolvedValue({
      entries: [
        {
          text_id: 43,
          cbeta_id: "T1579",
          title_zh: "瑜伽師地論",
          other_lang: "bo",
          pair_count: 39046,
          partner_count: 0,
          avg_confidence: null,
          sources: ["mitra"],
          sample_juan: 1,
          sample_partner_id: null,
          sample_partner_title: "",
        },
      ],
      total_pairs: 39046,
    });
  });

  it("folds catalog titles to simplified for 中文简体 readers", async () => {
    await i18n.changeLanguage("zh");
    renderPage();

    expect(await screen.findByText("瑜伽师地论")).toBeInTheDocument();
    expect(screen.queryByText("瑜伽師地論")).not.toBeInTheDocument();
  });

  it("keeps catalog titles traditional for 繁體 readers", async () => {
    await i18n.changeLanguage("zh-Hant");
    renderPage();

    expect(await screen.findByText("瑜伽師地論")).toBeInTheDocument();
    expect(screen.queryByText("瑜伽师地论")).not.toBeInTheDocument();
  });
});
