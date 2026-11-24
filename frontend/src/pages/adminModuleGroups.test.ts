import { describe, expect, it } from "vitest";
import { groupModuleEvents, MODULE_GROUPS } from "./adminModuleGroups";

const ev = (event_name: string, count: number, users: number) => ({ event_name, count, users });

describe("groupModuleEvents", () => {
  it("成对的「出现→点开」合成一行，转化率按人数算", () => {
    const { groups } = groupModuleEvents([ev("paste_locate_show", 575, 64), ev("paste_locate_click", 6, 5)]);
    const row = groups.find((g) => g.key === "chat")!.rows[0];
    expect(row).toMatchObject({ kind: "funnel", users: 64, count: 575, toUsers: 5, toCount: 6, rate: 7.8 });
  });

  it("点开为 0 时漏斗照样显示，转化 0%", () => {
    const { groups } = groupModuleEvents([ev("forgot_password_open", 12, 4)]);
    expect(groups.find((g) => g.key === "account")!.rows[0]).toMatchObject({ toUsers: 0, rate: 0 });
  });

  it("人数少于 3 的折进「其他」，次数再多也一样", () => {
    const { groups, other } = groupModuleEvents([ev("chat", 900, 260), ev("search_facet", 44, 2)]);
    expect(groups.find((g) => g.key === "search")).toBeUndefined();
    expect(other.map((r) => r.key)).toEqual(["search_facet"]);
  });

  it("异常组不因人数少被折叠", () => {
    const { groups } = groupModuleEvents([ev("trace_error", 2, 1)]);
    expect(groups).toEqual([expect.objectContaining({ key: "errors", danger: true })]);
  });

  it("没登记的事件不丢，进「其他」；纯反面事件不显示", () => {
    const { groups, other } = groupModuleEvents([ev("brand_new_event", 50, 30), ev("citation_panel_close", 20, 15)]);
    expect(groups).toEqual([]);
    expect(other).toEqual([expect.objectContaining({ key: "brand_new_event", fallback: "brand_new_event" })]);
  });

  it("同一事件不在两个板块重复登记", () => {
    const seen: string[] = [];
    for (const g of MODULE_GROUPS) {
      for (const r of g.rows) seen.push(...(r.kind === "single" ? [r.event] : [r.from, r.to]));
    }
    expect(new Set(seen).size).toBe(seen.length);
  });
});
