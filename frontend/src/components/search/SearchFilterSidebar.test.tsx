import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SearchFilterSidebar from "./SearchFilterSidebar";
import type { SearchFacets } from "../../api/client";
import type { FacetSelection } from "../../utils/searchFacets";

const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

const FACETS: SearchFacets = {
  canon: [
    { key: "xuzang", count: 3 },
    { key: "taisho", count: 12 },
  ],
  lang: [
    { key: "pi", count: 2 },
    { key: "lzh", count: 15 },
  ],
  // 后端按数量排；侧栏要按年代排，且「日本」放最后
  dynasty: [
    { key: "唐", count: 6 },
    { key: "日本", count: 4 },
    { key: "宋", count: 3 },
    { key: "東漢", count: 1 },
  ],
  section: [
    { key: "vinaya", count: 1 },
    { key: "prajna", count: 9 },
  ],
};

const NONE: FacetSelection = { canon: [], lang: [], dynasty: [], section: [] };

function names(group: Element): string[] {
  return [...group.querySelectorAll(".s-filter-name")].map((el) => el.textContent ?? "");
}

function groupByTitle(container: HTMLElement, title: string): Element {
  const t = [...container.querySelectorAll(".s-filter-title")].find((el) => el.textContent?.trim() === title);
  if (!t) throw new Error(`no group ${title}`);
  return t.closest(".s-filter-group")!;
}

describe("SearchFilterSidebar · 藏经/语言/朝代/部类", () => {
  it("四组标题按序，无 emoji，图标 aria-hidden", () => {
    const { container } = render(
      <SearchFilterSidebar facets={FACETS} selection={NONE} onToggle={() => {}} onClear={() => {}} />,
    );
    const titles = [...container.querySelectorAll(".s-filter-title")];
    expect(titles.map((el) => el.textContent?.trim())).toEqual(["藏经", "语言", "朝代（汉文）", "部类（大正藏）"]);
    for (const el of titles) {
      expect(el.textContent).not.toMatch(EMOJI);
      expect(el.querySelector(".anticon")).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("藏经/部类按藏经次序、朝代按年代、语言按数量，计数照后端", () => {
    const { container } = render(
      <SearchFilterSidebar facets={FACETS} selection={NONE} onToggle={() => {}} onClear={() => {}} />,
    );
    expect(names(groupByTitle(container, "藏经"))).toEqual(["大正藏", "卍续藏"]);
    expect(names(groupByTitle(container, "部类（大正藏）"))).toEqual(["般若部", "律部"]);
    expect(names(groupByTitle(container, "语言"))).toEqual(["汉文", "巴利文"]);
    // 「宋」不能借朝代表的别名显示成「北宋」——后端的宋含南宋
    expect(names(groupByTitle(container, "朝代（汉文）"))).toEqual(["东汉", "唐", "宋", "日本"]);
    const taisho = screen.getByText("大正藏").closest("label")!;
    expect(within(taisho).getByText("12")).toBeInTheDocument();
  });

  it("当前结果里没有取值的组整组不显示（如巴利文结果没有朝代/部类）", () => {
    const { container } = render(
      <SearchFilterSidebar
        facets={{ canon: [{ key: "pali", count: 5 }], lang: [{ key: "pi", count: 5 }], dynasty: [], section: [] }}
        selection={NONE}
        onToggle={() => {}}
        onClear={() => {}}
      />,
    );
    const titles = [...container.querySelectorAll(".s-filter-title")].map((el) => el.textContent?.trim());
    expect(titles).toEqual(["藏经", "语言"]);
  });

  it("已选但本次计数为 0 的项仍在且勾着（否则没法取消）；旧后端无计数时不显示假 0", () => {
    const sel: FacetSelection = { ...NONE, section: ["agama"], dynasty: ["隋"] };
    const { container, rerender } = render(
      <SearchFilterSidebar facets={FACETS} selection={sel} onToggle={() => {}} onClear={() => {}} />,
    );
    const agama = screen.getByText("阿含部").closest("label")!;
    expect(within(agama).getByRole("checkbox")).toBeChecked();
    expect(within(agama).getByText("0")).toBeInTheDocument();
    // 部类按大正藏次序：阿含部在般若部前
    expect(names(groupByTitle(container, "部类（大正藏）"))).toEqual(["阿含部", "般若部", "律部"]);

    rerender(<SearchFilterSidebar facets={undefined} selection={sel} onToggle={() => {}} onClear={() => {}} />);
    const agama2 = screen.getByText("阿含部").closest("label")!;
    expect(within(agama2).getByRole("checkbox")).toBeChecked();
    expect(agama2.querySelector(".s-filter-count")).toBeNull();
  });

  it("勾选回调带组名与取值；有已选时才出现「清除筛选」", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    const onClear = vi.fn();
    const { rerender } = render(
      <SearchFilterSidebar facets={FACETS} selection={NONE} onToggle={onToggle} onClear={onClear} />,
    );
    expect(screen.queryByRole("button", { name: "清除筛选" })).not.toBeInTheDocument();
    await user.click(screen.getByText("卍续藏"));
    expect(onToggle).toHaveBeenCalledWith("canon", "xuzang");

    rerender(
      <SearchFilterSidebar
        facets={FACETS}
        selection={{ ...NONE, canon: ["xuzang"] }}
        onToggle={onToggle}
        onClear={onClear}
      />,
    );
    await user.click(screen.getByRole("button", { name: "清除筛选" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
