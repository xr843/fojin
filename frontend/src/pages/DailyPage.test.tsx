import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DailyPage from "./DailyPage";

vi.mock("../utils/dailyPassage", () => ({
  pickDaily: () => ({
    dateKey: "2026-11-24",
    passage: {
      text: "應無所住而生其心",
      title_zh: "金剛般若波羅蜜經",
      cbeta_id: "T0235",
      text_id: 7,
      juan_num: 1,
      reader_path: "/texts/7/read?juan=1&anchor=p0749c22&hl=1949-1957",
    },
  }),
}));

function Loc() {
  const l = useLocation();
  return <div data-testid="loc">{l.pathname + l.search}</div>;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <DailyPage />
          <Loc />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe("每日一段页", () => {
  it("经名直达原文那一行；问小津带着原文与经名去问答页", () => {
    renderPage();
    expect(screen.getByText("今日一段 · 2026-11-24")).toBeInTheDocument();
    const src = screen.getByRole("link", { name: /金[剛刚]般若波[羅罗]蜜[經经]》卷1/ });
    expect(src.getAttribute("href")).toBe("/texts/7/read?juan=1&anchor=p0749c22&hl=1949-1957");
    fireEvent.click(screen.getByRole("button", { name: /问小津/ }));
    const params = new URL(screen.getByTestId("loc").textContent!, "http://x").searchParams;
    expect(params.get("context")).toBe("應無所住而生其心"); // 送原文（繁体原字），不送转换后的字形
    expect(params.get("source")).toBe("金剛般若波羅蜜經");
    expect(params.get("q")).toBeTruthy();
  });
});
