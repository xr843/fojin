import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import ProfilePage from "./ProfilePage";
import { useAuthStore } from "../stores/authStore";
import {
  getApiKeyStatus,
  getBookmarks,
  getHistory,
} from "../api/client";

vi.mock("../api/client", () => ({
  getApiKeyStatus: vi.fn(),
  getBookmarks: vi.fn(),
  getHistory: vi.fn(),
  saveApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  changePassword: vi.fn(),
}));

function renderPage(ui: ReactNode, initialPath = "/profile") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>,
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

describe("ProfilePage", () => {
  beforeEach(async () => {
    vi.mocked(getApiKeyStatus).mockResolvedValue({
      has_api_key: false,
      provider: null,
      model: null,
      key_preview: null,
    });
    vi.mocked(getBookmarks).mockResolvedValue({ total: 0, page: 1, size: 20, items: [] });
    vi.mocked(getHistory).mockResolvedValue({ total: 0, page: 1, size: 20, items: [] });
    useAuthStore.setState({ token: null, user: null });
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    vi.clearAllMocks();
    useAuthStore.setState({ token: null, user: null });
    await i18n.changeLanguage("zh");
  });

  it("renders the logged-out state in the active UI language", () => {
    renderPage(<ProfilePage />);

    expect(screen.getByText("Please log in first")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to log in" })).toBeInTheDocument();
  });

  it("renders profile metadata labels in the active UI language", () => {
    useAuthStore.setState({
      token: "token",
      user: {
        id: 1,
        username: "reader",
        email: "reader@example.com",
        display_name: null,
        role: "user",
        is_active: true,
        created_at: "2026-01-10T00:00:00Z",
      },
    });

    renderPage(<ProfilePage />);

    expect(screen.getByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getByText("Personal info")).toBeInTheDocument();
    expect(screen.getByText("Username")).toBeInTheDocument();
    expect(screen.getByText("Display name")).toBeInTheDocument();
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("Joined")).toBeInTheDocument();
  });
});
