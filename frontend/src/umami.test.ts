// 2026-11-22：访问统计把网址整串记下，/chat?q=<整句提问>、贴进搜索框的大段原文都进了统计库。
// 发送前去掉超过 20 字的 q / quote；短关键词（搜索词、辞典词）与 utm 等其他参数照留。
import { describe, expect, it } from "vitest";
import { scrubTrackedUrl, TRACKED_DOMAINS } from "./umami";

const href = (path: string) => `https://fojin.app${path}`;

describe("scrubTrackedUrl", () => {
  it("长提问从网址里去掉，utm 与其他参数照留", () => {
    const q = encodeURIComponent("请解释这句话的意思与出处：一时婆伽婆一切智人在王舍城耆阇崛山中");
    const out = scrubTrackedUrl(href(`/chat?q=${q}&send=1&utm_source=fojin.ai&utm_medium=trace`));
    expect(out).toBe(href("/chat?send=1&utm_source=fojin.ai&utm_medium=trace"));
  });

  it("短关键词保留", () => {
    const u = href(`/search?q=${encodeURIComponent("金刚经")}`);
    expect(scrubTrackedUrl(u)).toBe(u);
  });

  it("quote 参数同样处理；没有查询串、不是网址都原样返回", () => {
    const q = encodeURIComponent("一时婆伽婆一切智人在王舍城耆阇崛山中以神通力");
    expect(scrubTrackedUrl(href(`/texts/7/read?juan=1&quote=${q}`))).toBe(href("/texts/7/read?juan=1"));
    expect(scrubTrackedUrl(href("/chat"))).toBe(href("/chat"));
    expect(scrubTrackedUrl("")).toBe("");
  });
});

describe("TRACKED_DOMAINS", () => {
  it("只有 fojin.app 上报，镜像站与本机开发不上报", () => {
    expect(TRACKED_DOMAINS.split(",")).toEqual(["fojin.app", "www.fojin.app"]);
  });
});
