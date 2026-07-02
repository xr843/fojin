import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import SharedQAPage from "./SharedQAPage";
import { getSharedQA, type SharedQA } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getSharedQA: vi.fn(),
  };
});

function sharedQA(o: Partial<SharedQA> = {}): SharedQA {
  return {
    id: "qa_1",
    question: "What is emptiness?",
    answer: "Form is emptiness.",
    sources: [
      {
        text_id: 1 as SharedQA["sources"] extends Array<infer S> ? S extends { text_id: infer T } ? T : never : never,
        juan_num: 1,
        chunk_text: "照见五蕴皆空",
        score: 0.9,
        title_zh: "般若波罗蜜多心经",
      },
    ],
    view_count: 3,
    created_at: "2026-01-10T00:00:00Z",
    ...o,
  };
}

function renderPage() {
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={["/share/qa/qa_1"]}>
        <Routes>
          <Route path="/share/qa/:id" element={<SharedQAPage />} />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );
}

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", enTranslation, true, true);
});

describe("SharedQAPage", () => {
  beforeEach(async () => {
    vi.mocked(getSharedQA).mockResolvedValue(sharedQA());
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("zh");
  });

  it("renders shared Q&A chrome in the active UI language", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("What is emptiness?")).toBeInTheDocument());
    expect(screen.getByText("FoJin")).toBeInTheDocument();
    expect(screen.getAllByText(/AI Buddhist Q&A/).length).toBeGreaterThan(0);
    expect(screen.getByText("Question")).toBeInTheDocument();
    expect(screen.getByText("Answer")).toBeInTheDocument();
    expect(screen.getByText("Sources Cited")).toBeInTheDocument();
    expect(screen.getByText(/Fascicle 1/)).toBeInTheDocument();
    expect(screen.getByText("Ask your own Buddhist question?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open AI Q&A/ })).toBeInTheDocument();
    expect(screen.getByText("Viewed 3 times")).toBeInTheDocument();
  });

  it("renders not-found state in the active UI language", async () => {
    vi.mocked(getSharedQA).mockRejectedValueOnce(new Error("404"));

    renderPage();

    await waitFor(() => expect(screen.getByText("Share not found")).toBeInTheDocument());
    expect(screen.getByText("The link may have expired or been deleted.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Go to AI Q&A/ })).toBeInTheDocument();
  });
});
