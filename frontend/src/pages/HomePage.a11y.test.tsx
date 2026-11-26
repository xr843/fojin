/** 首页：功能卡是真链接（键盘可达）、游客提示关闭后记住、热门检索收进搜索下拉。 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router";
import HomePage from "./HomePage";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  const never = () => new Promise<never>(() => {});
  return { ...actual, getStats: vi.fn(never), getSources: vi.fn(never), getFilters: vi.fn(never), getHomeShowcase: vi.fn(never) };
});
vi.mock("../components/XiaojinPet", () => ({ default: () => null }));

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <HomePage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe("HomePage 无障碍与记忆", () => {
  beforeEach(() => localStorage.clear());

  it("五张功能卡都是带 href 的链接，键盘 Tab 能选中", () => {
    const { container } = renderHome();
    const cards = [...container.querySelectorAll<HTMLElement>(".home-feature-card")];
    expect(cards).toHaveLength(5);
    for (const c of cards) {
      expect(c.tagName).toBe("A");
      expect(c.getAttribute("href")).toMatch(/^\//);
      expect(c.tabIndex).toBe(0);
    }
    expect(cards.map((c) => c.getAttribute("href"))).toEqual(["/chat", "/read", "/dictionary", "/sources", "/history"]);
  });

  it("有阅读记录时，读经卡链接指向上次那一卷", () => {
    localStorage.setItem(
      "fojin-reading-history",
      JSON.stringify([{ textId: 8170, title: "永嘉证道歌", juan: 1, ratio: 0, ts: Date.now() }]),
    );
    const { container } = renderHome();
    expect(container.querySelectorAll(".home-feature-card")[1].getAttribute("href")).toBe("/texts/8170/read?juan=1");
  });

  it("游客提示关闭后写入存储，重新进入首页不再出现", () => {
    const first = renderHome();
    expect(first.container.querySelector(".home-tip")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "关闭提示" }));
    expect(first.container.querySelector(".home-tip")).toBeNull();
    first.unmount();

    const second = renderHome();
    expect(second.container.querySelector(".home-tip")).toBeNull();
  });

  it("热门检索不再单占一行：输入框为空时点开，下拉里列出热门词", async () => {
    const { container } = renderHome();
    expect(container.querySelector(".home-hot-tags")).toBeNull();
    const input = screen.getByRole("combobox");
    fireEvent.mouseDown(input);
    fireEvent.focus(input);
    expect(await screen.findByText("热门检索")).toBeTruthy();
    expect(await screen.findByText("金刚经")).toBeTruthy();
  });
});
