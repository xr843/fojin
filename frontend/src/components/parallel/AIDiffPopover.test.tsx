import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import AIDiffPopover from "./AIDiffPopover";
import type { AiDiffChunkInput, AiDiffResponse } from "../../api/client";

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

const chunks: AiDiffChunkInput[] = [
  { text_id: 100, juan_num: 1, chunk_index: 0, lang: "lzh", text: "觀自在菩薩。" },
  { text_id: 200, juan_num: 1, chunk_index: 0, lang: "en", text: "Avalokiteshvara." },
];

describe("AIDiffPopover", () => {
  it("renders loading state while fetching", () => {
    const fetcher = vi.fn(
      () => new Promise<AiDiffResponse>(() => {}),
    );
    render(wrap(<AIDiffPopover chunks={chunks} onClose={() => {}} fetchAiDiff={fetcher} />));
    expect(screen.getByText(/正在生成差异分析/)).toBeTruthy();
  });

  it("renders analysis sections on success", async () => {
    const response: AiDiffResponse = {
      cached: false,
      prompt_version: "v1",
      model: "deepseek-v4-pro",
      analysis: {
        summary: "两版核心一致。",
        differences: ["lzh 用观自在", "en 用音译"],
        doctrinal_notes: "无重要教义差异。",
      },
    };
    const fetcher = vi.fn(() => Promise.resolve(response));
    render(wrap(<AIDiffPopover chunks={chunks} onClose={() => {}} fetchAiDiff={fetcher} />));
    await waitFor(() => expect(screen.getByText(/两版核心一致/)).toBeTruthy());
    expect(screen.getByText(/lzh 用观自在/)).toBeTruthy();
    expect(screen.getByText(/无重要教义差异/)).toBeTruthy();
  });

  it("renders error state on failure", async () => {
    const fetcher = vi.fn(() => Promise.reject(new Error("boom")));
    render(wrap(<AIDiffPopover chunks={chunks} onClose={() => {}} fetchAiDiff={fetcher} />));
    await waitFor(() => expect(screen.getByText(/分析失败/)).toBeTruthy());
  });

  it("renders cached badge when response.cached is true", async () => {
    const response: AiDiffResponse = {
      cached: true,
      prompt_version: "v1",
      model: "deepseek-v4-pro",
      analysis: { summary: "x", differences: [], doctrinal_notes: "" },
    };
    const fetcher = vi.fn(() => Promise.resolve(response));
    render(wrap(<AIDiffPopover chunks={chunks} onClose={() => {}} fetchAiDiff={fetcher} />));
    await waitFor(() => expect(screen.getByText(/缓存/)).toBeTruthy());
  });
});
