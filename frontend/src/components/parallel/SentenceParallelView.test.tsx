import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import SentenceParallelView from "./SentenceParallelView";
import {
  getSentenceParallels,
  type SentenceAlignmentResponse,
  type SentencePair,
} from "../../api/client";

// mock API client
vi.mock("../../api/client", () => ({
  getSentenceParallels: vi.fn(),
}));

const mockGet = vi.mocked(getSentenceParallels);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function pair(overrides: Partial<SentencePair> = {}): SentencePair {
  return {
    side_a: { char_start: 0, char_end: 5, lang: "lzh", text: "如是我聞。" },
    side_b: {
      text_id: 9,
      juan_num: 1,
      char_start: 0,
      char_end: 14,
      lang: "pi",
      title: "MN 10",
      text: "Evaṁ me sutaṁ.",
    },
    similarity: 0.94,
    align_type: "1-2",
    method: "sentence-bertalign",
    is_verified: true,
    ...overrides,
  };
}

function resp(pairs: SentencePair[]): SentenceAlignmentResponse {
  return { text_id: 1, juan_num: 5, total: pairs.length, pairs };
}

describe("SentenceParallelView", () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it("renders sentence pairs with both languages and align_type badge", async () => {
    mockGet.mockResolvedValue(resp([pair()]));
    render(<SentenceParallelView textId={1} juanNum={5} />, { wrapper });
    expect(await screen.findByText("如是我聞。")).toBeInTheDocument();
    expect(screen.getByText("Evaṁ me sutaṁ.")).toBeInTheDocument();
    // align_type badge for 1-2
    expect(screen.getByText(/1→2/)).toBeInTheDocument();
    // counterpart title
    expect(screen.getByText("MN 10")).toBeInTheDocument();
    // verified marker
    expect(screen.getByText("已校")).toBeInTheDocument();
  });

  it("does not show an align badge for a 1-1 pair", async () => {
    mockGet.mockResolvedValue(resp([pair({ align_type: "1-1" })]));
    render(<SentenceParallelView textId={1} juanNum={5} />, { wrapper });
    expect(await screen.findByText("如是我聞。")).toBeInTheDocument();
    expect(screen.queryByText(/1→2/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2→1/)).not.toBeInTheDocument();
  });

  it("shows Empty when total is 0", async () => {
    mockGet.mockResolvedValue(resp([]));
    render(<SentenceParallelView textId={1} juanNum={5} />, { wrapper });
    expect(await screen.findByText(/暂无逐句对齐|No sentence-level/)).toBeInTheDocument();
  });

  it("shows an alert on error", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    render(<SentenceParallelView textId={1} juanNum={5} />, { wrapper });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("click-to-pin: clicking a card activates it, clicking again clears", async () => {
    const pairA = pair({ side_a: { char_start: 0, char_end: 5, lang: "lzh", text: "第一句。" } });
    const pairB = pair({ side_a: { char_start: 5, char_end: 10, lang: "lzh", text: "第二句。" } });
    mockGet.mockResolvedValue(resp([pairA, pairB]));
    render(<SentenceParallelView textId={1} juanNum={5} />, { wrapper });
    const cards = await screen.findAllByTestId("sentence-pair-card");
    expect(cards).toHaveLength(2);

    fireEvent.click(cards[0]);
    expect(cards[0].className).toMatch(/is-active/);
    expect(cards[1].className).not.toMatch(/is-active/);

    fireEvent.click(cards[0]);
    expect(cards[0].className).not.toMatch(/is-active/);
  });
});
