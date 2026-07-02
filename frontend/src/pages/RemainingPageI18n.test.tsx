import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactElement } from "react";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import type { IIIFManifestId, SourceId, TextId } from "../types/branded";
import AdminAnswerQualityPage from "./AdminAnswerQualityPage";
import AdminDashboardPage from "./AdminDashboardPage";
import HomePage from "./HomePage";
import ManuscriptViewerPage from "./ManuscriptViewerPage";
import ParallelReaderPage from "./ParallelReaderPage";
import SutraLandingPage from "./SutraLandingPage";
import TopicsPage from "./TopicsPage";
import {
  getAdminActiveUsers,
  getAdminModuleUsage,
  getAdminOverview,
  getAdminTrends,
  getAnswerQualityQueue,
  getAnswerReviewStats,
  getFilters,
  getStats,
  getTextDetail,
  getTextManifests,
  getTextRelations,
  type ActiveUserDayDetail,
  type AdminModuleUsage,
  type AdminOverview,
  type AdminTrends,
  type AnswerQueueResponse,
  type AnswerReviewStats,
  type TextDetail,
} from "../api/client";
import { getPlatformActivity, type PlatformActivity } from "../api/feed";
import { useAuthStore } from "../stores/authStore";

vi.mock("@ant-design/charts", () => ({
  DualAxes: () => <div data-testid="dual-axes" />,
}));

vi.mock("../components/IIIFViewer", () => ({
  default: () => <div data-testid="iiif-viewer" />,
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getAdminActiveUsers: vi.fn(),
    getAdminModuleUsage: vi.fn(),
    getAdminOverview: vi.fn(),
    getAdminTrends: vi.fn(),
    getAnswerQualityQueue: vi.fn(),
    getAnswerReviewStats: vi.fn(),
    getFilters: vi.fn(),
    getStats: vi.fn(),
    getSources: vi.fn(),
    getTextDetail: vi.fn(),
    getTextManifests: vi.fn(),
    getTextRelations: vi.fn(),
    getJuanAlignment: vi.fn(),
    getParallelRead: vi.fn(),
    submitAnswerReview: vi.fn(),
  };
});

vi.mock("../api/feed", () => ({
  getPlatformActivity: vi.fn(),
}));

function renderWithProviders(ui: ReactElement, initialEntries = ["/"]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
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
  new_messages_yesterday: 5,
  pending_suggestions: 1,
  pending_annotations: 2,
  last_updated: "2026-07-02T08:00:00Z",
};

const trends: AdminTrends = {
  registrations: [{ date: "2026-07-02", count: 2 }],
  messages: [{ date: "2026-07-02", count: 4 }],
  active_users: [{ date: "2026-07-02", count: 1 }],
};

const activeUsers: ActiveUserDayDetail = {
  date: "2026-07-02",
  total: 1,
  users: [
    {
      user_id: 1 as ActiveUserDayDetail["users"][number]["user_id"],
      username: "reader",
      display_name: "Reader",
      email: "reader@example.com",
      role: "admin",
      chat_messages: 3,
      texts_read: 2,
      last_active_at: "2026-07-02T08:00:00Z",
      api_provider: "openai",
    },
  ],
};

const moduleUsage: AdminModuleUsage = {
  days: 7,
  events: [{ event_name: "search", label: "Search", count: 9 }],
  top_search_keywords: [{ keyword: "lotus", count: 3 }],
  answer_quality: {
    chat_questions: 10,
    citation_click: 5,
    chat_copy: 2,
    chat_retry: 1,
    citation_click_rate: 50,
    copy_rate: 20,
    retry_rate: 10,
  },
};

const platformActivity: PlatformActivity = {
  period_days: 7,
  reading: {
    total_reads: 8,
    unique_texts_read: 2,
    top_texts: [{ text_id: 1, title_zh: "Lotus Sutra", read_count: 4 }],
  },
  chat: {
    total_messages: 20,
    total_sessions: 5,
    positive_feedback: 3,
    negative_feedback: 1,
    assistant_messages: 10,
    assistant_no_source: 1,
  },
  users: {
    new_users: 2,
    active_users: 4,
    returning_users: 2,
    byok_active_users: 1,
  },
  content: {
    new_texts: 0,
    total_texts: 100,
    total_sources: 10,
  },
};

const answerQueue: AnswerQueueResponse = {
  total_unreviewed: 1,
  score_distribution: { p10: 0.1, p25: 0.2, p50: 0.5, p90: 0.9 },
  items: [
    {
      message_id: 1,
      session_id: 10,
      question: "What is emptiness?",
      answer: "A concise answer.",
      sources: [],
      reason_tags: ["weak_evidence"],
      suspicion_score: 8.5,
      feedback: null,
      created_at: "2026-07-02T08:00:00Z",
    },
  ],
};

const answerStats: AnswerReviewStats = {
  reviewed_total: 5,
  good: 3,
  bad: 2,
  by_category: {},
  last_reviewed_at: "2026-07-02T08:00:00Z",
};

const textDetail: TextDetail = {
  id: 1 as TextDetail["id"],
  taisho_id: null,
  cbeta_id: "T0001",
  title_zh: "Sample Text",
  title_sa: null,
  title_bo: null,
  title_pi: null,
  translator: null,
  dynasty: null,
  fascicle_count: 1,
  category: null,
  subcategory: null,
  cbeta_url: null,
  has_content: true,
  content_char_count: 100,
  lang: "lzh",
  created_at: "2026-07-02T08:00:00Z",
};

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

describe("remaining page i18n", () => {
  beforeEach(async () => {
    vi.mocked(getAdminOverview).mockResolvedValue(overview);
    vi.mocked(getAdminTrends).mockResolvedValue(trends);
    vi.mocked(getAdminActiveUsers).mockResolvedValue(activeUsers);
    vi.mocked(getAdminModuleUsage).mockResolvedValue(moduleUsage);
    vi.mocked(getPlatformActivity).mockResolvedValue(platformActivity);
    vi.mocked(getAnswerQualityQueue).mockResolvedValue(answerQueue);
    vi.mocked(getAnswerReviewStats).mockResolvedValue(answerStats);
    vi.mocked(getTextRelations).mockResolvedValue({
      text_id: 1 as TextId,
      title_zh: "Sample Text",
      relations: [],
    });
    vi.mocked(getTextDetail).mockResolvedValue(textDetail);
    vi.mocked(getTextManifests).mockResolvedValue([
      {
        id: 1 as IIIFManifestId,
        text_id: 1 as TextId,
        source_id: 1 as SourceId,
        label: "Scan set",
        manifest_url: "https://example.com/manifest.json",
        thumbnail_url: null,
        provider: "iiif",
        rights: null,
      },
    ]);
    vi.mocked(getStats).mockResolvedValue({ total_texts: 100, source_count: 5 });
    vi.mocked(getFilters).mockResolvedValue({
      dynasties: [],
      categories: [],
      languages: [],
      languages_all: [],
      sources: [],
    });
    useAuthStore.setState({ token: null, user: null });
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("zh");
  });

  it("renders admin dashboard chrome in the active UI language", async () => {
    renderWithProviders(<AdminDashboardPage />);

    await waitFor(() => expect(screen.getByText("Total users")).toBeInTheDocument());
    expect(screen.getByText("Recent 30-day trend")).toBeInTheDocument();
    expect(screen.getAllByText("Platform activity").length).toBeGreaterThan(0);
    expect(screen.getByText("Module usage")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Answer quality")).toBeInTheDocument());
    expect(screen.getByText("Popular search terms (Top 10)")).toBeInTheDocument();
  });

  it("renders answer-quality review details in the active UI language", async () => {
    renderWithProviders(<AdminAnswerQualityPage />);

    await waitFor(() => expect(screen.getByText(/Recall distribution/)).toBeInTheDocument());
    const expandButton = document.querySelector(".ant-table-row-expand-icon");
    expect(expandButton).not.toBeNull();
    fireEvent.click(expandButton!);
    expect(screen.getByText("Question:")).toBeInTheDocument();
    expect(screen.getByText("Answer:")).toBeInTheDocument();
    expect(screen.getByText(/^Current feedback:/)).toBeInTheDocument();
    expect(screen.getByText("Retrieved passages:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark good" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark bad" })).toBeInTheDocument();
    expect(screen.getByText("Failure type (required for bad)")).toBeInTheDocument();
  });

  it("renders parallel-reader empty state in the active UI language", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/parallel/:textId" element={<ParallelReaderPage />} />
      </Routes>,
      ["/parallel/1"],
    );

    await waitFor(() => expect(screen.getByRole("heading", { name: /Parallel cross-canon comparison/ })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.getByText("Compare version:")).toBeInTheDocument();
    expect(screen.getByText("Please choose a comparison text")).toBeInTheDocument();
  });

  it("renders manuscript viewer chrome in the active UI language", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/texts/:textId/manuscripts" element={<ManuscriptViewerPage />} />
      </Routes>,
      ["/texts/1/manuscripts"],
    );

    await waitFor(() => expect(screen.getByText("Available images")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: /Manuscript images/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View" })).toBeInTheDocument();
  });

  it("renders sutra landing chrome in the active UI language", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/sutras/:slug" element={<SutraLandingPage />} />
      </Routes>,
      ["/sutras/heart-sutra"],
    );

    expect(screen.getByText(/Home/)).toBeInTheDocument();
    expect(screen.getByText("Popular sutras")).toBeInTheDocument();
    expect(screen.getByText("Text introduction")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start reading/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Text details/ })).toBeInTheDocument();
    expect(screen.getByText("More popular sutras")).toBeInTheDocument();
    expect(screen.getByText(/Scripture data provided by/)).toBeInTheDocument();
  });

  it("renders topics page chrome in the active UI language", async () => {
    renderWithProviders(<TopicsPage />);

    expect(screen.getByRole("heading", { name: "Classic Topics" })).toBeInTheDocument();
    expect(screen.getByText(/topics/)).toBeInTheDocument();
    fireEvent.click(document.querySelector(".topic-card-header")!);
    expect(screen.getByRole("button", { name: /Search related texts on FoJin/ })).toBeInTheDocument();
  });

  it("renders home visitor tip in the active UI language", async () => {
    renderWithProviders(<HomePage />);

    expect(screen.getByText(/Search and browse without an account/)).toBeInTheDocument();
    expect(screen.getByText("Sign in")).toBeInTheDocument();
  });
});
