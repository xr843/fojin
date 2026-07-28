import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import i18n from "../i18n";
import AlignmentReviewPage from "./AlignmentReviewPage";
import {
  getAlignmentCandidates,
  reviewAlignmentCandidate,
  type AlignmentCandidate,
} from "../api/client";

vi.mock("../api/client", () => ({
  getAlignmentCandidates: vi.fn(),
  reviewAlignmentCandidate: vi.fn(),
}));

beforeAll(() => {
  i18n.changeLanguage("zh");
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
  if (!window.ResizeObserver) {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof window.ResizeObserver;
  }
});

function candidate(o: Partial<AlignmentCandidate> = {}): AlignmentCandidate {
  return {
    id: 1,
    text_a_id: 100,
    text_a_title: "妙法莲华经",
    text_a_juan_num: 1,
    text_a_lang: "lzh",
    text_b_id: 200,
    text_b_title: "Saddharmapundarika",
    text_b_juan_num: 1,
    text_b_lang: "san",
    similarity: 0.912,
    source: "knn-bootstrap",
    status: "pending",
    ...o,
  };
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/admin/alignment/review"]}>
        <AlignmentReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AlignmentReviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders pending candidates with similarity and source tags", async () => {
    vi.mocked(getAlignmentCandidates).mockResolvedValue([
      candidate({ id: 1 }),
      candidate({
        id: 2,
        text_a_title: "金刚经",
        similarity: 0.831,
        source: "anchor-expansion",
      }),
    ]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("妙法莲华经")).toBeInTheDocument();
    });
    expect(screen.getByText("金刚经")).toBeInTheDocument();
    expect(screen.getByText("91.2%")).toBeInTheDocument();
    // source labels rendered via i18n, not the raw enum
    expect(screen.getByText("kNN 引导")).toBeInTheDocument();
    expect(screen.getByText("锚点扩展")).toBeInTheDocument();
    expect(getAlignmentCandidates).toHaveBeenCalledWith(50);
  });

  it("accepts a candidate, calls the API, and removes the row", async () => {
    vi.mocked(getAlignmentCandidates).mockResolvedValue([
      candidate({ id: 1 }),
      candidate({ id: 2, text_a_title: "金刚经", similarity: 0.831 }),
    ]);
    vi.mocked(reviewAlignmentCandidate).mockResolvedValue(
      candidate({ id: 1, status: "accepted" }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("妙法莲华经")).toBeInTheDocument();
    });

    // AntD auto-inserts a space between two CJK chars in buttons ("接 受"),
    // so match tolerant of whitespace.
    const acceptButtons = screen.getAllByRole("button", { name: /接\s*受/ });
    fireEvent.click(acceptButtons[0]);

    await waitFor(() => {
      expect(reviewAlignmentCandidate).toHaveBeenCalledWith(1, true);
    });
    await waitFor(() => {
      expect(screen.queryByText("妙法莲华经")).not.toBeInTheDocument();
    });
    // the untouched candidate remains
    expect(screen.getByText("金刚经")).toBeInTheDocument();
  });

  it("shows the empty state when there are no candidates", async () => {
    vi.mocked(getAlignmentCandidates).mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText("暂无待复核的候选对齐"),
      ).toBeInTheDocument();
    });
    expect(reviewAlignmentCandidate).not.toHaveBeenCalled();
  });
});
