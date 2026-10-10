import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import SearchFilterSidebar from "./SearchFilterSidebar";

const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

describe("SearchFilterSidebar 分面标题", () => {
  it("国家/地区、馆藏标题不含 emoji，改用线性图标", () => {
    const { container } = render(
      <SearchFilterSidebar
        regions={["日本"]}
        regionCounts={{ 日本: 1 }}
        regionFilter={new Set()}
        onToggleRegion={() => {}}
        institutions={[{ name: "SAT", nameEn: "SAT", count: 1 }]}
        institutionFilter={new Set()}
        onToggleInstitution={() => {}}
      />,
    );
    const titles = [...container.querySelectorAll(".s-filter-title")];
    expect(titles.map((el) => el.textContent?.trim())).toEqual(["国家/地区", "馆藏"]);
    for (const el of titles) {
      expect(el.textContent).not.toMatch(EMOJI);
      expect(el.querySelector(".anticon")).toHaveAttribute("aria-hidden", "true");
    }
  });
});
