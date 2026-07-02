import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import type { ReactElement } from "react";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import AdminAnnotationsPage from "./AdminAnnotationsPage";
import AdminAuditLogPage from "./AdminAuditLogPage";
import AdminFeedbacksPage from "./AdminFeedbacksPage";
import AdminSuggestionsPage from "./AdminSuggestionsPage";
import AdminUsersPage from "./AdminUsersPage";
import { useAuthStore } from "../stores/authStore";
import {
  getAdminAnnotations,
  getAdminAuditLog,
  getAdminFeedbacks,
  getAdminUsers,
  getSourceSuggestions,
  type AdminAnnotationItem,
  type AdminAuditLogItem,
  type AdminFeedbackItem,
  type AdminUserItem,
  type SourceSuggestionItem,
} from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getAdminAnnotations: vi.fn(),
    getAdminAuditLog: vi.fn(),
    getAdminFeedbacks: vi.fn(),
    getAdminUsers: vi.fn(),
    getSourceSuggestions: vi.fn(),
    reviewAnnotation: vi.fn(),
    updateAdminUser: vi.fn(),
    updateFeedbackStatus: vi.fn(),
    replyFeedback: vi.fn(),
    updateSuggestionStatus: vi.fn(),
    deleteSourceSuggestion: vi.fn(),
  };
});

function paginated<T>(items: T[]) {
  return {
    total: items.length,
    page: 1,
    size: 20,
    items,
  };
}

function renderPage(ui: ReactElement) {
  return render(
    <HelmetProvider>
      {ui}
    </HelmetProvider>,
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

describe("Admin CRUD pages", () => {
  beforeEach(async () => {
    vi.mocked(getAdminFeedbacks).mockResolvedValue(paginated<AdminFeedbackItem>([
      {
        id: 1,
        user_id: 1 as AdminFeedbackItem["user_id"],
        username: "reader",
        content: "Please add a source.",
        contact: "reader@example.com",
        status: "pending",
        admin_reply: null,
        replied_at: null,
        created_at: "2026-07-01T08:00:00Z",
      },
    ]));
    vi.mocked(getSourceSuggestions).mockResolvedValue(paginated<SourceSuggestionItem>([
      {
        id: 2,
        name: "New Source",
        url: "https://example.com",
        description: "Useful archive",
        status: "pending",
        submitted_at: "2026-07-01T08:00:00Z",
      },
    ]));
    vi.mocked(getAdminAnnotations).mockResolvedValue(paginated<AdminAnnotationItem>([
      {
        id: 3 as AdminAnnotationItem["id"],
        text_id: 1 as AdminAnnotationItem["text_id"],
        juan_num: 1,
        annotation_type: "note",
        content: "Needs review",
        user_id: 1 as AdminAnnotationItem["user_id"],
        username: "reader",
        status: "pending",
        created_at: "2026-07-01T08:00:00Z",
      },
    ]));
    vi.mocked(getAdminAuditLog).mockResolvedValue(paginated<AdminAuditLogItem>([
      {
        id: 4,
        actor_id: 1,
        actor_username: "admin",
        action: "update_user",
        target_type: "user",
        target_id: 9,
        detail: { role: { from: "user", to: "admin" }, is_active: true, custom_field: "raw value" },
        created_at: "2026-07-01T08:00:00Z",
      },
    ]));
    vi.mocked(getAdminUsers).mockResolvedValue(paginated<AdminUserItem>([
      {
        id: 5 as AdminUserItem["id"],
        username: "reader",
        display_name: "Reader",
        email: "reader@example.com",
        role: "user",
        is_active: true,
        created_at: "2026-07-01T08:00:00Z",
        last_active_at: "2026-07-02T08:00:00Z",
      },
    ]));
    useAuthStore.setState({
      token: "token",
      user: {
        id: 5,
        username: "reader",
        email: "reader@example.com",
        display_name: "Reader",
        role: "user",
        is_active: true,
        created_at: "2026-07-01T08:00:00Z",
      },
    });
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    vi.clearAllMocks();
    useAuthStore.setState({ token: null, user: null });
    await i18n.changeLanguage("zh");
  });

  it("renders feedback management chrome in the active UI language", async () => {
    renderPage(<AdminFeedbacksPage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "User feedback" })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Please add a source.")).toBeInTheDocument());
    expect(screen.getByText("Feedback")).toBeInTheDocument();
    expect(screen.getByText("Contact")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reply" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark as read" })).toBeInTheDocument();
  });

  it("renders source suggestion management chrome in the active UI language", async () => {
    renderPage(<AdminSuggestionsPage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Source suggestions" })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("New Source")).toBeInTheDocument());
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getAllByText("Pending review").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Accept/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Delete/ })).toBeInTheDocument();
  });

  it("renders annotation review chrome in the active UI language", async () => {
    renderPage(<AdminAnnotationsPage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Annotation review" })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Needs review")).toBeInTheDocument());
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Note")).toBeInTheDocument();
    expect(screen.getAllByText("Pending review").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Approve/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/ })).toBeInTheDocument();
  });

  it("renders audit log chrome in the active UI language", async () => {
    renderPage(<AdminAuditLogPage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Audit log" })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("User update")).toBeInTheDocument());
    expect(screen.getByText("Actor")).toBeInTheDocument();
    expect(screen.getByText("Action")).toBeInTheDocument();
    expect(screen.getByText("User update")).toBeInTheDocument();
    expect(screen.getByText(/Role:/)).toBeInTheDocument();
    expect(screen.getByText(/Account status:/)).toBeInTheDocument();
    expect(screen.getByText(/custom_field: raw value/)).toBeInTheDocument();
  });

  it("renders user management chrome in the active UI language", async () => {
    renderPage(<AdminUsersPage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "User management" })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("reader@example.com")).toBeInTheDocument());
    expect(screen.getByText("Username")).toBeInTheDocument();
    expect(screen.getByText("Display name")).toBeInTheDocument();
    expect(screen.getByText("Registered")).toBeInTheDocument();
    expect(screen.getByText("Last active")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search username or email")).toBeInTheDocument();
  });
});
