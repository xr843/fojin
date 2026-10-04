import { describe, it, expect } from "vitest";
import type { TFunction } from "i18next";
import { prettifySource } from "./kgProvenance";
import zh from "../../public/locales/zh/translation.json";

const dict = zh as unknown as Record<string, string>;
// 用真实 zh 文案做 t，断言的是读者实际看到的字，而不是 key 名
const t = ((key: string, opts?: Record<string, string>) =>
  (dict[key] ?? key).replace(/\{\{(\w+)\}\}/g, (_, k) => opts?.[k] ?? "")) as unknown as TFunction;

describe("prettifySource 图谱关系来源", () => {
  it("程序抽取的关系明说未经人工校订，而不是露出内部代码", () => {
    const label = prettifySource(t, "auto:cbeta_cf_note");
    expect(label).toBe("程序自动抽取，未经人工校订");
    expect(label).not.toContain("auto:");
  });

  it("CBETA 元数据也标明是程序抽取", () => {
    expect(prettifySource(t, "auto:cbeta_metadata")).toContain("程序抽取");
  });

  it("经录来源带出经号", () => {
    expect(prettifySource(t, "cbeta_xml:catalog:T2154")).toBe("CBETA 经录（T2154）");
  });

  it("人工校订与权威规范库照常显示", () => {
    expect(prettifySource(t, "seed:concept_network")).toBe("人工校订");
    expect(prettifySource(t, "dila")).toBe("DILA 规范库");
    expect(prettifySource(t, "dila_catalog")).toBe("DILA 规范目录");
  });

  it("未知来源原样返回（不编造）", () => {
    expect(prettifySource(t, "something_new")).toBe("something_new");
  });
});
