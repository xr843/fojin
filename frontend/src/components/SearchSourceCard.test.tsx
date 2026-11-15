/** 搜索页「出处」卡片：只对像原文的查询发核对请求；只把经/律/论当出处显示。 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import SearchSourceCard from "./SearchSourceCard";
import { verifyQuote, type QuoteVerdict } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, verifyQuote: vi.fn() };
});

const T0235: QuoteVerdict = {
  quote: "应无所住而生其心",
  verbatim: true,
  matches_capped: false,
  matches: [
    { text_id: 7, cbeta_id: "T0235", title_zh: "金剛般若波羅蜜經", juan_num: 1, reader_url: null, canon_class: "sutra" },
    { text_id: 900, cbeta_id: "X0468", title_zh: "金剛經註解", juan_num: 2, reader_url: null, canon_class: "commentary" },
  ],
};

function renderCard(query: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SearchSourceCard query={query} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SearchSourceCard", () => {
  beforeEach(() => {
    vi.mocked(verifyQuote).mockReset();
  });

  it("原文查询：显示原典、卷号，链接到阅读器那一卷和核对页", async () => {
    vi.mocked(verifyQuote).mockResolvedValue(T0235);
    renderCard("应无所住而生其心");
    const title = await screen.findByRole("link", { name: "《金剛般若波羅蜜經》第1卷" });
    expect(title.getAttribute("href")).toBe("/texts/7/read?juan=1");
    expect(screen.getByText("T0235")).toBeTruthy();
    expect(screen.getByRole("link", { name: /逐字核对/ }).getAttribute("href")).toBe(
      `/verify?q=${encodeURIComponent("应无所住而生其心")}`,
    );
    expect(verifyQuote).toHaveBeenCalledWith("应无所住而生其心");
  });

  it("最早一部是注疏/经录时不显示", async () => {
    vi.mocked(verifyQuote).mockResolvedValue({
      ...T0235,
      matches: [{ ...T0235.matches[0], canon_class: "history", title_zh: "入唐新求聖教目錄" }],
    });
    const { container } = renderCard("一切如来心秘密全身舍利");
    await waitFor(() => expect(verifyQuote).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector(".s-source-card")).toBeNull();
  });

  it("接口出错时不显示，也不影响页面", async () => {
    vi.mocked(verifyQuote).mockImplementation(async () => {
      throw new Error("429");
    });
    const { container } = renderCard("应无所住而生其心");
    await waitFor(() => expect(verifyQuote).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector(".s-source-card")).toBeNull();
  });

  it("短词、问句、经名都不发核对请求", async () => {
    for (const q of ["金刚经", "心如工画师出自哪部经", "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經"]) {
      const { unmount } = renderCard(q);
      unmount();
    }
    await new Promise((r) => setTimeout(r, 0));
    expect(verifyQuote).not.toHaveBeenCalled();
  });
});
