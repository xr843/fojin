import { describe, expect, it } from "vitest";
import {
  ASK_PREFIX,
  askQueryFrom,
  buildHomeSuggestOptions,
  itemsFromSuggestResponse,
  looksLikeQuestion,
} from "./homeSuggest";

const t = (key: string, opts?: Record<string, unknown>) =>
  key === "home.suggest_ask" ? `问小津：${opts?.q as string}` : key;

describe("首页联想的分组与「问小津」行", () => {
  it("按 type 分组：经名 / 词条 / 热门问题，组内保持后端顺序；经名类查询「问小津」在最后", () => {
    const groups = buildHomeSuggestOptions(
      [
        { value: "金剛般若波羅蜜經", type: "title" },
        { value: "金刚", type: "term" },
        { value: "金剛頂瑜伽理趣般若經", type: "title" },
        { value: "金刚石", type: "term" },
        { value: "《金刚经》四句偈的真正含义是什么？", type: "question" },
      ],
      "金刚",
      t,
    );
    expect(groups.map((g) => g.label)).toEqual([
      "home.suggest_group_title",
      "home.suggest_group_term",
      "home.suggest_group_question",
      "home.suggest_group_ask",
    ]);
    expect(groups[0].options.map((o) => o.value)).toEqual(["金剛般若波羅蜜經", "金剛頂瑜伽理趣般若經"]);
    expect(groups[1].options.map((o) => o.value)).toEqual(["金刚", "金刚石"]);
  });

  it("问句：「问小津」行在最前（下拉是虚拟列表，放最后要滚动才看得见）", () => {
    const groups = buildHomeSuggestOptions(
      [{ value: "應無所住", type: "term" }],
      "应无所住而生其心是什么意思",
      t,
    );
    expect(groups[0].label).toBe("home.suggest_group_ask");
    const ask = groups[0].options[0];
    expect(ask.value).toBe(`${ASK_PREFIX}应无所住而生其心是什么意思`);
    expect(ask.label).toBe("问小津：应无所住而生其心是什么意思");
    expect(groups[1].label).toBe("home.suggest_group_term");
  });

  it("没有联想时也有「问小津」这一行；空组不出现", () => {
    const groups = buildHomeSuggestOptions([], "玄奘", t);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("home.suggest_group_ask");
  });

  it("looksLikeQuestion：问号/疑问词/长句算问题，经名、词头、人名不算", () => {
    expect(looksLikeQuestion("般若是什么")).toBe(true);
    expect(looksLikeQuestion("What is nirvana")).toBe(true);
    expect(looksLikeQuestion("六祖为什么说本来无一物？")).toBe(true);
    expect(looksLikeQuestion("金刚经")).toBe(false);
    expect(looksLikeQuestion("玄奘")).toBe(false);
    expect(looksLikeQuestion("般若波羅蜜多心經")).toBe(false);
    expect(looksLikeQuestion("  ")).toBe(false);
  });

  it("askQueryFrom：识别问小津行并还原问句；普通选项返回 null", () => {
    expect(askQueryFrom(`${ASK_PREFIX}般若是什么`)).toBe("般若是什么");
    expect(askQueryFrom("般若波羅蜜多心經")).toBeNull();
    expect(askQueryFrom("")).toBeNull();
  });

  it("空白查询不出任何组（含问小津）", () => {
    expect(buildHomeSuggestOptions([], "   ", t)).toEqual([]);
  });

  it("旧后端只回 suggestions 字符串时，全部当作经名（不丢联想）", () => {
    expect(itemsFromSuggestResponse({ suggestions: ["心經", "法華經"] })).toEqual([
      { value: "心經", type: "title" },
      { value: "法華經", type: "title" },
    ]);
    expect(itemsFromSuggestResponse({ suggestions: ["心經"], items: [{ value: "心經", type: "term" }] })).toEqual([
      { value: "心經", type: "term" },
    ]);
  });
});
