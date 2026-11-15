/** 首页：功能卡是真链接（键盘可达）、游客提示关闭后记住、热门检索带点击埋点。 */
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
    expect(cards.map((c) => c.getAttribute("href"))).toEqual(["/chat", "/read", "/dictionary", "/sources", "/kg"]);
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

  it("热门检索按钮带点击埋点，事件属性是标签原文", () => {
    const { container } = renderHome();
    const tags = [...container.querySelectorAll<HTMLElement>(".home-hot-tag")];
    expect(tags.length).toBeGreaterThan(0);
    for (const b of tags) {
      expect(b.dataset.umamiEvent).toBe("home_hot_tag");
      expect(b.dataset.umamiEventTag).toBe(b.textContent);
    }
  });
});
