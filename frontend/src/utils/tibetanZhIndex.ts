import type { TibetanZhItem } from "../api/tibetanZh";

// 部（索引里的 part 字段值）→ 界面文案键；也决定分组顺序。
export const PART_KEYS: Array<[string, string]> = [
  ["甘珠尔", "tibetanZh.part_kangyur"], // i18n-exempt
  ["丹珠尔", "tibetanZh.part_tengyur"], // i18n-exempt
  ["松绷", "tibetanZh.part_sungbum"], // i18n-exempt
];

export interface PartGroup {
  part: string;
  labelKey: string | null;
  cats: Array<{ cat: string; items: TibetanZhItem[] }>;
  count: number;
}

/** 按 部 → 部类 分组；部按甘珠尔/丹珠尔/松绷排，部类与各部内条目保持索引原顺序。 */
export function groupItems(items: TibetanZhItem[]): PartGroup[] {
  const groups = new Map<string, PartGroup>();
  for (const it of items) {
    let g = groups.get(it.part);
    if (!g) {
      g = { part: it.part, labelKey: PART_KEYS.find(([p]) => p === it.part)?.[1] ?? null, cats: [], count: 0 };
      groups.set(it.part, g);
    }
    let c = g.cats.find((x) => x.cat === it.cat);
    if (!c) {
      c = { cat: it.cat, items: [] };
      g.cats.push(c);
    }
    c.items.push(it);
    g.count++;
  }
  const order = (p: string) => {
    const i = PART_KEYS.findIndex(([k]) => k === p);
    return i === -1 ? PART_KEYS.length : i;
  };
  return [...groups.values()].sort((a, b) => order(a.part) - order(b.part));
}
