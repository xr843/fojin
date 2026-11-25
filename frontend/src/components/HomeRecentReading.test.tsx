/** 首页「接着读」：一行最多 3 条、显示卷号、× 移除会写回存储并通知父组件、清空后整栏消失。 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import HomeRecentReading from "./HomeRecentReading";
import { getReadingHistory, recordReading } from "../utils/readingHistory";

function seed(n: number) {
  for (let i = 1; i <= n; i++) recordReading({ textId: i, title: `经${i}`, juan: i, ratio: 0 });
}

function renderBar(onChange = vi.fn()) {
  const r = render(
    <MemoryRouter>
      <HomeRecentReading initial={getReadingHistory()} onChange={onChange} />
    </MemoryRouter>,
  );
  return { ...r, onChange };
}

describe("HomeRecentReading", () => {
  beforeEach(() => localStorage.clear());

  it("最多显示 3 条，最新的在前，带卷号，链接直达那一卷", () => {
    seed(7);
    renderBar();
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain("《经7》");
    expect(items[0].textContent).toContain("第7卷");
    expect(items[0].querySelector("a")?.getAttribute("href")).toBe("/texts/7/read?juan=7");
  });

  it("点 × 移除：存储里删掉、列表少一条且由第 4 条补位、通知父组件", () => {
    seed(7);
    const { onChange } = renderBar();
    fireEvent.click(screen.getByRole("button", { name: "从最近阅读中移除《经7》" }));

    expect(getReadingHistory().map((e) => e.textId)).toEqual([6, 5, 4, 3, 2, 1]);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain("《经6》");
    expect(items[2].textContent).toContain("《经4》");
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].map((e: { textId: number }) => e.textId)).toEqual([6, 5, 4, 3, 2, 1]);
  });

  it("没有记录不渲染；删光最后一条后整栏消失", () => {
    const empty = renderBar();
    expect(empty.container.querySelector(".home-recent")).toBeNull();
    empty.unmount();

    seed(1);
    const { container } = renderBar();
    fireEvent.click(screen.getByRole("button", { name: "从最近阅读中移除《经1》" }));
    expect(container.querySelector(".home-recent")).toBeNull();
  });
});
