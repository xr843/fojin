/**
 * 搜索页分面：藏经 / 语言 / 朝代 / 部类。
 *
 * 取值与后端 services/search_facets.py 一一对应（藏经按 cbeta_id 前缀、部类按大正藏编号
 * 区间，查询时现算，不依赖索引里的 category 字段——生产那个字段几乎全是「大正藏」）。
 * 选中项全部写在 URL 里，逗号分隔多选，可分享、可后退：
 *   canon=taisho,xuzang  tl=lzh  dynasty=唐,宋  section=prajna
 * 语言沿用 `tl`（#709：`lang` 与 i18next 的界面语言参数撞名）。
 */
import type { SearchFacets } from "../api/client";
import { resolveDynasty } from "../data/dynasty_years";

export type FacetGroup = "canon" | "lang" | "dynasty" | "section";

export const FACET_GROUPS: readonly FacetGroup[] = ["canon", "lang", "dynasty", "section"];

/** 每组在 URL 里的参数名。 */
export const FACET_URL_PARAM: Record<FacetGroup, string> = {
  canon: "canon",
  lang: "tl",
  dynasty: "dynasty",
  section: "section",
};

/** 与后端 CANONS 同序。 */
export const CANON_CODES = ["taisho", "xuzang", "jiaxing", "nanchuan", "pali", "kangyur", "gretil"] as const;

/** 与后端 SECTIONS 同序（大正藏编号顺序）。 */
export const SECTION_CODES = [
  "agama", "jataka", "prajna", "lotus", "avatamsaka", "ratnakuta", "nirvana", "mahasamnipata",
  "sutra_collection", "esoteric", "vinaya", "sutra_treatise", "abhidharma", "madhyamaka", "yogacara",
  "treatise_collection", "sutra_commentary", "vinaya_commentary", "treatise_commentary", "schools",
  "history", "encyclopedia", "non_buddhist", "catalogue", "j_sutra_commentary", "j_vinaya_commentary",
  "j_treatise_commentary", "j_schools", "siddham", "dunhuang", "apocrypha",
] as const;

export type FacetSelection = Record<FacetGroup, string[]>;

export function splitMulti(value: string | null | undefined): string[] {
  const out: string[] = [];
  for (const part of (value ?? "").split(",")) {
    const v = part.trim();
    if (v && !out.includes(v)) out.push(v);
  }
  return out;
}

/**
 * 从 URL 读出四组已选项。`legacyLang` 是旧链接里还当作文本语言用的 `?lang=`
 * （只有在没有 `tl` 时才生效，判定在 SearchPage 里）。
 */
export function readFacetSelection(params: URLSearchParams, legacyLang = ""): FacetSelection {
  return {
    canon: splitMulti(params.get("canon")),
    lang: splitMulti(params.get("tl") || legacyLang),
    dynasty: splitMulti(params.get("dynasty")),
    section: splitMulti(params.get("section")),
  };
}

export function toggleValue(values: string[], key: string): string[] {
  return values.includes(key) ? values.filter((v) => v !== key) : [...values, key];
}

export function countSelected(sel: FacetSelection): number {
  return FACET_GROUPS.reduce((n, g) => n + sel[g].length, 0);
}

/** 传给后端的筛选参数：空组不传（保持与旧请求完全一样）。 */
export function facetQueryParams(sel: FacetSelection): {
  canon?: string;
  lang?: string;
  dynasty?: string;
  section?: string;
} {
  const join = (v: string[]) => (v.length ? v.join(",") : undefined);
  return { canon: join(sel.canon), lang: join(sel.lang), dynasty: join(sel.dynasty), section: join(sel.section) };
}

/** 非中国的「朝代」（日本撰述等）排在最后。 */
const NON_CHINESE_PERIODS = new Set(["india", "japan", "korea", "tibet"]);

/** 朝代按年代排：东汉 → 三国 → 两晋 … → 清，后端给的是按数量排。 */
export function dynastySortKey(name: string): number {
  const d = resolveDynasty(name);
  if (!d) return 100000;
  if (NON_CHINESE_PERIODS.has(d.key)) return 50000 + d.start;
  return d.start;
}

/** 组内条目：有计数的 + 已选但本次计数为 0 的（否则选中项会消失、没法取消）。 */
export function facetItems(
  group: FacetGroup,
  facets: SearchFacets | null | undefined,
  selected: string[],
): Array<{ key: string; count: number | null }> {
  const counts = new Map((facets?.[group] ?? []).map((b) => [b.key, b.count]));
  const keys = [...counts.keys()];
  for (const k of selected) if (!counts.has(k)) keys.push(k);
  const order = (k: string): number => {
    if (group === "canon") return (CANON_CODES as readonly string[]).indexOf(k) >>> 0;
    if (group === "section") return (SECTION_CODES as readonly string[]).indexOf(k) >>> 0;
    if (group === "dynasty") return dynastySortKey(k);
    return -(counts.get(k) ?? 0); // 语言按数量
  };
  // 本组没有计数（旧后端副本不返回 facets）时已选项不标数字，免得显示成假的 0。
  const known = facets?.[group] !== undefined;
  return keys
    .sort((a, b) => order(a) - order(b))
    .map((key) => ({ key, count: counts.get(key) ?? (known ? 0 : null) }));
}
