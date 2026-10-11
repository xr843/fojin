import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  CANON_CODES,
  SECTION_CODES,
  dynastySortKey,
  facetQueryParams,
  readFacetSelection,
  splitMulti,
  toggleValue,
} from "./searchFacets";

const ROOT = resolve(__dirname, "../..");

describe("searchFacets", () => {
  it("取值表与后端 services/search_facets.py 同序同码", () => {
    const py = readFileSync(resolve(ROOT, "../backend/app/services/search_facets.py"), "utf8");
    const sections = [...py.matchAll(/^\s+\("([a-z_]+)", \d+, \d+\),/gm)].map((m) => m[1]);
    const canonBlock = py.slice(py.indexOf("CANONS: dict"), py.indexOf("}", py.indexOf("CANONS: dict")));
    const canons = [...canonBlock.matchAll(/^\s+"([a-z]+)":/gm)].map((m) => m[1]);
    expect(sections).toEqual([...SECTION_CODES]);
    expect(canons).toEqual([...CANON_CODES]);
  });

  it("每个藏经/部类取值三语都有译名", () => {
    for (const loc of ["zh", "zh-Hant", "en"]) {
      const dict = JSON.parse(readFileSync(resolve(ROOT, `public/locales/${loc}/translation.json`), "utf8"));
      for (const c of CANON_CODES) expect(dict[`search.canon.${c}`], `${loc} canon ${c}`).toBeTruthy();
      for (const c of SECTION_CODES) expect(dict[`search.section.${c}`], `${loc} section ${c}`).toBeTruthy();
      for (const g of ["canon", "lang", "dynasty", "section"]) expect(dict[`search.facet_${g}`]).toBeTruthy();
    }
  });

  it("URL ⇄ 选择：多选逗号分隔、去重；tl 优先于旧 lang；空组不传参", () => {
    const sel = readFacetSelection(new URLSearchParams("canon=taisho,,xuzang,taisho&dynasty=唐&tl=lzh"), "pi");
    expect(sel).toEqual({ canon: ["taisho", "xuzang"], lang: ["lzh"], dynasty: ["唐"], section: [] });
    expect(readFacetSelection(new URLSearchParams(""), "pi").lang).toEqual(["pi"]);
    expect(facetQueryParams(sel)).toEqual({ canon: "taisho,xuzang", lang: "lzh", dynasty: "唐", section: undefined });
    expect(splitMulti(null)).toEqual([]);
    expect(toggleValue(["a", "b"], "a")).toEqual(["b"]);
    expect(toggleValue(["b"], "a")).toEqual(["b", "a"]);
  });

  it("朝代按年代排，日本撰述殿后，未知值最后", () => {
    // 生产上实际出现的 16 个朝代值（2026-10-11）
    const prod = ["唐", "宋", "明", "清", "隋", "西晉", "南朝", "元", "東漢", "三國", "東晉", "十六國", "日本", "北朝", "遼", "金"];
    const sorted = [...prod, "某朝"].sort((a, b) => dynastySortKey(a) - dynastySortKey(b));
    expect(sorted).toEqual([
      "東漢", "三國", "西晉", "十六國", "東晉", "北朝", "南朝", "隋", "唐", "遼", "宋", "金", "元", "明", "清", "日本", "某朝",
    ]);
  });
});
