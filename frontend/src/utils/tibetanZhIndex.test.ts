import { describe, expect, it } from "vitest";
import type { TibetanZhItem } from "../api/tibetanZh";
import { groupItems } from "./tibetanZhIndex";

const item = (id: string, part: string, cat: string): TibetanZhItem => ({
  id, title: id, au: "", part, cat, rv: "", md: null, pdf: null, docx: null,
});

describe("groupItems", () => {
  it("部按 甘珠尔/丹珠尔/松绷 排，未知的部排最后；部类与条目保持索引顺序", () => {
    const groups = groupItems([
      item("S-1", "松绷", "中观"),
      item("X-1", "其他", "杂"),
      item("T-2", "丹珠尔", "唯识部"),
      item("T-1", "丹珠尔", "中观部"),
      item("T-3", "丹珠尔", "唯识部"),
      item("K-1", "甘珠尔", "经部"),
    ]);
    expect(groups.map((g) => g.part)).toEqual(["甘珠尔", "丹珠尔", "松绷", "其他"]);
    const tengyur = groups[1];
    expect(tengyur.count).toBe(3);
    expect(tengyur.cats.map((c) => c.cat)).toEqual(["唯识部", "中观部"]);
    expect(tengyur.cats[0].items.map((i) => i.id)).toEqual(["T-2", "T-3"]);
    expect(tengyur.labelKey).toBe("tibetanZh.part_tengyur");
    expect(groups[3].labelKey).toBeNull();
  });
});
