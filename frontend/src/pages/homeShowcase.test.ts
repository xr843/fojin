import { describe, expect, it } from "vitest";
import { fitSourceNames, pickHan } from "./homeShowcase";

describe("pickHan", () => {
  it("简体界面用简体版", () => {
    expect(pickHan("攝大乘論", "摄大乘论", "zh")).toBe("摄大乘论");
    expect(pickHan("攝大乘論", "摄大乘论", "en")).toBe("摄大乘论");
  });
  it("繁体界面保留原文", () => {
    expect(pickHan("攝大乘論", "摄大乘论", "zh-Hant")).toBe("攝大乘論");
  });
  it("旧缓存没有简体版时回退原文", () => {
    expect(pickHan("攝大乘論", undefined, "zh")).toBe("攝大乘論");
  });
});

describe("fitSourceNames", () => {
  it("两个短名能放下就都放", () => {
    expect(fitSourceNames(["CBETA", "佛光大辞典", "SuttaCentral 巴利三藏"])).toEqual(["CBETA", "佛光大辞典"]);
  });
  it("第一个名字就很长时只放这一个，不再拼第二个", () => {
    expect(fitSourceNames(["佛光山电子大藏经", "巴利专名辞典", "CBETA"])).toEqual(["佛光山电子大藏经"]);
  });
  it("空数组返回空", () => {
    expect(fitSourceNames([])).toEqual([]);
  });
});
