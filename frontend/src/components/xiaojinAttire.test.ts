import { describe, expect, it } from "vitest";

import { ATTIRE_DOT, traditionToAttire } from "./xiaojinAttire";

describe("traditionToAttire", () => {
  // 生产 /api/chat/masters 的 15 条真实 tradition 字符串（2026-08-08 实测），
  // 一条不落——后端改字符串导致换装失灵时，这里先红。
  it.each([
    ["印度·中观", "indian"], // 龙树
    ["天台宗", "han"], // 智顗
    ["禅宗", "han"], // 慧能
    ["法相唯识宗", "han"], // 玄奘
    ["华严宗", "han"], // 法藏
    ["三论宗/中观", "indian"], // 鸠摩罗什
    ["净土宗", "han"], // 印光
    ["天台/净土·跨宗派", "han"], // 蕅益
    ["禅宗·五宗兼嗣", "han"], // 虚云
    ["藏传·噶举派", "kagyu"], // 米拉日巴
    ["南传·泰国森林禅林派", "theravada"], // 阿姜查
    ["藏传·格鲁派", "gelug"], // 宗喀巴
    ["藏传·噶当派 (印藏桥梁)", "gelug"], // 阿底峡——含「印」字但必须归格鲁装
    ["南传·上座部论师", "theravada"], // 觉音
    ["南传·缅甸内观传统", "theravada"], // 马哈希
  ] as const)("%s → %s", (tradition, expected) => {
    expect(traditionToAttire(tradition)).toBe(expected);
  });

  it("空值与未知传承一律兜底汉传", () => {
    expect(traditionToAttire(null)).toBe("han");
    expect(traditionToAttire(undefined)).toBe("han");
    expect(traditionToAttire("")).toBe("han");
    expect(traditionToAttire("某个未来新加的传承")).toBe("han");
  });

  it("每个变体都有菜单色点", () => {
    const variants = ["han", "indian", "theravada", "gelug", "kagyu"] as const;
    for (const v of variants) {
      expect(ATTIRE_DOT[v]).toMatch(/^#[0-9a-f]{6}$/);
    }
  });
});
