import { describe, expect, it } from "vitest";
import type { QuoteMatch, QuoteVerdict } from "../api/client";
import { looksLikeSourceQuery, pickSourceMatch } from "./searchSource";

describe("looksLikeSourceQuery", () => {
  it("一段原文（≥8 汉字、非问句、非经名）才去查出处", () => {
    expect(looksLikeSourceQuery("应无所住而生其心")).toBe(true);
    expect(looksLikeSourceQuery("又有四門起諸煩惱，能令有情與生等苦和合不離。")).toBe(true);
    expect(looksLikeSourceQuery("一切有为法 如梦幻泡影")).toBe(true);
  });

  it("短词、术语不查", () => {
    expect(looksLikeSourceQuery("金刚经")).toBe(false);
    expect(looksLikeSourceQuery("般若波罗蜜多")).toBe(false);
    expect(looksLikeSourceQuery("Diamond Sutra")).toBe(false);
  });

  it("问句不查（去问小津）", () => {
    expect(looksLikeSourceQuery("心如工画师出自哪部经")).toBe(false);
    expect(looksLikeSourceQuery("有相唯识和无相唯识的区别在哪里")).toBe(false);
    expect(looksLikeSourceQuery("六度中有布施，四摄中也有布施。两者有何异同？")).toBe(false);
  });

  it("在找一部书的（经名结尾、书名号）不查", () => {
    expect(looksLikeSourceQuery("大佛頂如來密因修證了義諸菩薩萬行首楞嚴經")).toBe(false);
    expect(looksLikeSourceQuery("佛说大乘圣无量寿决定光明王如来陀罗尼经")).toBe(false);
    expect(looksLikeSourceQuery("《佛说一切如来真实摄大乘现证三昧大教王经》")).toBe(false);
    expect(looksLikeSourceQuery("大乘百法明門論註")).toBe(false);
  });
});

const m = (over: Partial<QuoteMatch>): QuoteMatch => ({
  text_id: 7, cbeta_id: "T0235", title_zh: "金剛般若波羅蜜經", juan_num: 1, reader_url: null, canon_class: "sutra", ...over,
});
const v = (over: Partial<QuoteVerdict>): QuoteVerdict => ({ quote: "x", verbatim: true, matches: [m({})], matches_capped: false, ...over });

describe("pickSourceMatch", () => {
  it("逐字命中且第一条是经/律/论 → 用它", () => {
    expect(pickSourceMatch(v({}))?.cbeta_id).toBe("T0235");
    expect(pickSourceMatch(v({ matches: [m({ canon_class: "treatise", cbeta_id: "T1558" })] }))?.cbeta_id).toBe("T1558");
    expect(pickSourceMatch(v({ matches: [m({ canon_class: "vinaya", cbeta_id: "T1428" })] }))?.cbeta_id).toBe("T1428");
  });

  it("没有逐字命中 → 不显示（near-miss 不能当出处）", () => {
    expect(pickSourceMatch(v({ verbatim: false }))).toBeNull();
    expect(pickSourceMatch(v({ matches: [] }))).toBeNull();
    expect(pickSourceMatch(undefined)).toBeNull();
  });

  it("排第一的是经录/史传/语录/注疏 → 不显示，免得把错的「出处」摆在最上面", () => {
    // 生产实测：「一切如来心秘密全身」按编号第一条是《入唐新求聖教目錄》——只列了经名
    for (const c of ["history", "school", "commentary", "later", "apocrypha", "unknown"] as const) {
      expect(pickSourceMatch(v({ matches: [m({ canon_class: c })] }))).toBeNull();
    }
    expect(pickSourceMatch(v({ matches: [m({ canon_class: null })] }))).toBeNull();
  });
});
