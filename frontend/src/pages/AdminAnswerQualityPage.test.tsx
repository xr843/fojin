import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";

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

  it("请求失败时显示错误态,而不是渲染成「队列已清空」", async () => {
    vi.mocked(getAnswerQualityQueue).mockRejectedValueOnce(new Error("boom"));
    vi.mocked(getAnswerReviewStats).mockResolvedValueOnce({
      reviewed_total: 0, good: 0, bad: 0, by_category: {}, last_reviewed_at: null,
    });

    render(<AdminAnswerQualityPage />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/队列已清空/)).not.toBeInTheDocument();
    expect(screen.queryByText(/未复核\s*0\s*条/)).not.toBeInTheDocument();
  });

  it("点击重试按钮后,请求成功并清除错误态", async () => {
    // 清除之前的 mock 设置,本测试使用独立的 mock 配置
    vi.mocked(getAnswerQualityQueue).mockClear();
    vi.mocked(getAnswerReviewStats).mockClear();

    // 第一次失败,第二次成功
    vi.mocked(getAnswerQualityQueue)
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce({
        total_unreviewed: 1,
        score_distribution: { p10: 0.2, p25: 0.3, p50: 0.5, p90: 0.9 },
        tag_distribution: { abnormal: 1 },
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

    render(<AdminAnswerQualityPage />);

    // 1. 等待错误横幅出现
    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();

    // 2. 点击 Alert 内的重试按钮
    const retryButton = within(alert).getByRole("button");
    fireEvent.click(retryButton);

    // 3. 断言 getAnswerQualityQueue 被调用了第二次
    await waitFor(
      () => {
        expect(vi.mocked(getAnswerQualityQueue)).toHaveBeenCalledTimes(2);
      },
      { timeout: 3000 },
    );

    // 4. 断言错误横幅消失
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    // 5. 断言"未复核 1 条"出现
    await waitFor(() => {
      expect(screen.getByText("未复核 1 条")).toBeInTheDocument();
    });
  });
});
