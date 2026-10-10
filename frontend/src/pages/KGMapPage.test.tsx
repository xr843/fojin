import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import "../i18n";
import KGMapPage from "./KGMapPage";

// deck.gl / maplibre need WebGL — jsdom has none. The toolbar is what's under test.
vi.mock("../components/kg-map/DeckGLMap", () => ({ default: () => <div data-testid="deck-map" /> }));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getKGGeoEntities: vi.fn().mockResolvedValue({
      entities: [{ id: 1, name_zh: "大慈恩寺", entity_type: "monastery", latitude: 34.2, longitude: 108.9 }],
    }),
    getKGLineageArcs: vi.fn().mockResolvedValue({ arcs: [] }),
  };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/map"]}>
          <KGMapPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe("KGMapPage toolbar", () => {
  it("toggles 纯中文 when the text label is tapped, not only the 28px switch", async () => {
    renderPage();
    await screen.findByTestId("deck-map");
    const sw = screen.getByRole("switch");
    expect(sw).toHaveAttribute("aria-checked", "false");
    // Mobile users aim at the words; the bare switch is a 28×16 target.
    fireEvent.click(screen.getByText("纯中文:"));
    expect(sw).toHaveAttribute("aria-checked", "true");
  });

  it("gives the switch an accessible name from its label", async () => {
    renderPage();
    await screen.findByTestId("deck-map");
    expect(screen.getByRole("switch", { name: /纯中文/ })).toBeInTheDocument();
  });
});
