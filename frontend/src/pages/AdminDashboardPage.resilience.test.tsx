import { Component, type ReactElement, type ReactNode } from "react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import AdminDashboardPage from "./AdminDashboardPage";
import {
  getAdminOverview,
  getAdminTrends,
  getAdminActiveUsers,
  getAdminModuleUsage,
  type AdminOverview,
} from "../api/client";
import { getPlatformActivity } from "../api/feed";

// The dashboard's trend chart is a heavy canvas component; stub it out.
vi.mock("@ant-design/charts", () => ({
  DualAxes: () => <div data-testid="dual-axes" />,
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getAdminOverview: vi.fn(),
    getAdminTrends: vi.fn(),
    getAdminActiveUsers: vi.fn(),
    getAdminModuleUsage: vi.fn(),
  };
});

vi.mock("../api/feed", () => ({
  getPlatformActivity: vi.fn(),
}));

// Mirrors the app-level ErrorBoundary that, in production, caught the crash and
// rendered "加载失败" over the whole admin route. If AdminDashboardPage throws
// during render, this boundary trips and shows the sentinel.
class CrashSentinel extends Component<{ children: ReactNode }, { crashed: boolean }> {
  state = { crashed: false };
  static getDerivedStateFromError() {
    return { crashed: true };
  }
  render() {
    return this.state.crashed ? <div data-testid="crashed" /> : this.props.children;
  }
}

function renderWithProviders(ui: ReactElement, client: QueryClient) {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <CrashSentinel>{ui}</CrashSentinel>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

const overview: AdminOverview = {
  total_users: 10,
  new_users_today: 2,
  new_users_yesterday: 1,
  total_sessions: 20,
  new_sessions_today: 3,
  new_sessions_yesterday: 2,
  total_messages: 50,
  new_messages_today: 4,
  new_messages_yesterday: 3,
  pending_suggestions: 0,
  pending_annotations: 0,
  last_updated: "2026-07-08T00:00:00Z",
};

describe("AdminDashboardPage resilience to transient stats failures", () => {
  beforeEach(() => {
    // Sub-cards only mount once the main content renders (which it never does in
    // these tests), so these queries are never actually invoked — keep the mocks
    // harmless and correctly typed just in case.
    vi.mocked(getAdminActiveUsers).mockResolvedValue({ date: "2026-07-08", total: 0, users: [] });
    vi.mocked(getAdminModuleUsage).mockResolvedValue(
      {} as Awaited<ReturnType<typeof getAdminModuleUsage>>,
    );
    vi.mocked(getPlatformActivity).mockResolvedValue(
      {} as Awaited<ReturnType<typeof getPlatformActivity>>,
    );
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // Regression for the prod incident: a burst of backend 503s left the trends
  // query neither loading nor error yet with undefined data — React Query
  // status:'pending' + fetchStatus:'idle', so isLoading (=isPending && isFetching)
  // is false and isError is false, but data is still undefined. The old code did
  // `const trends = trendsQuery.data!` and then `trends.messages.map(...)`, which
  // threw and took the whole admin route down via the ErrorBoundary ("加载失败，
  // 请刷新后重试"). The page must instead degrade to a spinner and never crash.
  //
  // We reproduce that exact pending+idle window deterministically: hold the trends
  // fetch open, let overview resolve, then cancel the in-flight trends query.
  it("does not crash while the trends query is pending with no data (transient 503 window)", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.mocked(getAdminOverview).mockResolvedValue(overview);
    // Never resolves on its own -> stays fetching until we cancel it.
    vi.mocked(getAdminTrends).mockReturnValue(
      new Promise<never>(() => {}) as ReturnType<typeof getAdminTrends>,
    );

    renderWithProviders(<AdminDashboardPage />, client);

    // Overview has resolved; trends is still in flight -> spinner, no crash yet.
    await waitFor(() => expect(getAdminTrends).toHaveBeenCalled());
    expect(screen.queryByTestId("crashed")).toBeNull();

    // Cancel the in-flight trends fetch: the query is now status:'pending' +
    // fetchStatus:'idle' with undefined data — the precise state the 503 burst
    // produced, and the one that used to throw at `trends.messages`.
    await act(async () => {
      await client.cancelQueries({ queryKey: ["adminTrends", 30] });
    });

    // Must not have white-screened; degrades to a spinner instead.
    expect(screen.queryByTestId("crashed")).toBeNull();
    expect(document.querySelector(".ant-spin")).not.toBeNull();
  });
});
