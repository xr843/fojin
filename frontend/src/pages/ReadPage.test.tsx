import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import ReadPage from "./ReadPage";
import { browseTaisho } from "../api/client";
import { TAISHO_SECTIONS } from "../data/taishoSections";

const scrollSpy = vi.fn();

beforeAll(() => {
  // jsdom 不实现 scrollIntoView
  Element.prototype.scrollIntoView = scrollSpy;
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
});

vi.mock("../api/client", () => ({ browseTaisho: vi.fn() }));
const mockBrowse = vi.mocked(browseTaisho);

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname + loc.search}</div>;
}

function renderPage(entry = "/read") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/read" element={<><ReadPage /><LocationProbe /></>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  mockBrowse.mockReset();
  scrollSpy.mockReset();
  i18n.changeLanguage("zh");
});

describe("读经页", () => {
  it("没有阅读记录时不显示「继续读」，有记录时链到上次的卷", () => {
    const { unmount } = renderPage();
    expect(screen.queryByText("继续读")).toBeNull();
    unmount();

    localStorage.setItem(
      "fojin-reading-history",
      JSON.stringify([{ textId: 9, title: "般若波羅蜜多心經", juan: 1, ratio: 0.3, ts: 1 }]),
    );
    renderPage();
    expect(screen.getByText("继续读")).toBeInTheDocument();
    // 简体界面把繁体经名转成简体
    const link = screen.getByText("《般若波罗蜜多心经》").closest("a");
    expect(link).toHaveAttribute("href", "/texts/9/read?juan=1");
  });

  it("已在「继续读」里的经不在常读经典里重复", () => {
    localStorage.setItem(
      "fojin-reading-history",
      JSON.stringify([{ textId: 7, title: "金刚般若波罗蜜经", juan: 1, ratio: 0.1, ts: 1 }]),
    );
    renderPage();
    // 金刚经（text 7）只在继续读里出现一次，指向续读位置
    const links = [...document.querySelectorAll('a[href^="/texts/7"]')].map((a) => a.getAttribute("href"));
    expect(links).toEqual(["/texts/7/read?juan=1"]);
    expect(document.querySelector('a[href="/texts/9"]')).not.toBeNull(); // 心经仍在常读经典
  });

  it("常读经典链到经文页", () => {
    renderPage();
    expect(screen.getByText("常读经典")).toBeInTheDocument();
    expect(document.querySelector('a[href="/texts/9"]')).not.toBeNull(); // 心经
  });

  it("部类按钮用简体名；点开按编号区间取经目、写进 ?bu=，再点一次收起", async () => {
    mockBrowse.mockResolvedValue([
      { id: 101, cbeta_id: "T0001", title_zh: "長阿含經", translator: "佛陀耶舍共竺佛念", dynasty: "後秦", fascicle_count: 22 },
    ]);
    renderPage();
    expect(screen.getByRole("button", { name: "华严部" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "華嚴部" })).toBeNull();

    const agama = TAISHO_SECTIONS[0];
    fireEvent.click(screen.getByRole("button", { name: "阿含部" }));
    await waitFor(() => expect(mockBrowse).toHaveBeenCalledWith(agama.from, agama.to));
    expect(await screen.findByText("长阿含经")).toHaveAttribute("href", "/texts/101");
    expect(screen.getByText("1 部可读")).toBeInTheDocument();
    expect(screen.getByTestId("loc").textContent).toBe(`/read?bu=${encodeURIComponent("阿含部")}`);
    expect(scrollSpy).toHaveBeenCalledTimes(1); // 点开后把经目滚进视野

    fireEvent.click(screen.getByRole("button", { name: "阿含部" }));
    expect(screen.getByTestId("loc").textContent).toBe("/read");
    expect(screen.queryByText("长阿含经")).toBeNull();
  });

  it("带 ?bu= 直接打开时就列出该部（可分享）", async () => {
    mockBrowse.mockResolvedValue([]);
    renderPage(`/read?bu=${encodeURIComponent("般若部")}`);
    await waitFor(() => expect(mockBrowse).toHaveBeenCalledWith(220, 261));
    expect(await screen.findByText("这一部暂无可在线阅读的经文")).toBeInTheDocument();
    expect(scrollSpy).not.toHaveBeenCalled(); // 直接打开分享链接时不抢滚动位置
  });

  it("部类区间覆盖全部大正藏编号 1–2920 且首尾相接", () => {
    expect(TAISHO_SECTIONS[0].from).toBe(1);
    expect(TAISHO_SECTIONS[TAISHO_SECTIONS.length - 1].to).toBe(2920);
    for (let i = 1; i < TAISHO_SECTIONS.length; i++) {
      expect(TAISHO_SECTIONS[i].from).toBe(TAISHO_SECTIONS[i - 1].to + 1);
    }
  });
});
