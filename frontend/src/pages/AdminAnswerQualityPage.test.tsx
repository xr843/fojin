import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import AdminAnswerQualityPage from "./AdminAnswerQualityPage";
import {
  getAnswerQualityQueue,
  getAnswerReviewStats,
} from "../api/client";

vi.mock("../api/client", () => ({
  getAnswerQualityQueue: vi.fn(),
  getAnswerReviewStats: vi.fn(),
  submitAnswerReview: vi.fn(),
}));

beforeAll(() => {
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
});

describe("AdminAnswerQualityPage", () => {
  beforeEach(() => {
    vi.mocked(getAnswerQualityQueue).mockResolvedValue({
      total_unreviewed: 1,
      score_distribution: { p10: 0.2, p25: 0.3, p50: 0.5, p90: 0.9 },
      tag_distribution: { "abnormal": 1 },
      items: [
        {
          message_id: 10,
          session_id: 5,
          question: "什么是五蕴？",
          answer: "很短",
          sources: [],
          reason_tags: ["abnormal"],
          suspicion_score: 3,
          feedback: null,
          created_at: "2026-07-02T00:00:00Z",
        },
      ],
    });
    vi.mocked(getAnswerReviewStats).mockResolvedValue({
      reviewed_total: 3,
      good: 2,
      bad: 1,
      by_category: { recall: 1 },
      last_reviewed_at: "2026-07-01T00:00:00Z",
    });
  });

  it("shows queue summary, review stats, and calibration controls", async () => {
    render(<AdminAnswerQualityPage />);

    await waitFor(() => {
      expect(screen.getByText("未复核 1 条")).toBeInTheDocument();
    });
    expect(screen.getByText("已复核 3 条")).toBeInTheDocument();
    expect(screen.getByText("good 2")).toBeInTheDocument();
    expect(screen.getByText("bad 1")).toBeInTheDocument();
    expect(screen.getByText("时间窗口")).toBeInTheDocument();
    expect(screen.getByText("最低可疑度")).toBeInTheDocument();
    expect(screen.getByText("什么是五蕴？")).toBeInTheDocument();
    expect(getAnswerReviewStats).toHaveBeenCalledTimes(1);
  });
});
