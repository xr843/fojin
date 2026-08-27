import { beforeEach, describe, expect, it } from "vitest";
import {
  FIRST_TOKEN_SAMPLES_KEY,
  expectedFirstTokenSeconds,
  recordFirstTokenMs,
} from "./firstTokenStats";

/** 等待预期的原料：本机最近几次「首字耗时」。推理模型首字要等 24-180 秒，
 *  用户不知道该等多久，等不及就手动停止再发。中位数比均值稳（一次 180 秒的
 *  极端值不该把预期拉到离谱）。 */
describe("firstTokenStats", () => {
  beforeEach(() => localStorage.clear());

  it("没有样本 → null（界面不显示预期，而不是显示 0 秒）", () => {
    expect(expectedFirstTokenSeconds()).toBeNull();
  });

  it("取中位数并四舍五入到秒", () => {
    [38000, 120000, 42000].forEach(recordFirstTokenMs);
    expect(expectedFirstTokenSeconds()).toBe(42);
  });

  it("只保留最近 5 个样本", () => {
    [1, 2, 3, 4, 5, 6].map((n) => n * 10000).forEach(recordFirstTokenMs);
    expect(JSON.parse(localStorage.getItem(FIRST_TOKEN_SAMPLES_KEY)!))
      .toEqual([20000, 30000, 40000, 50000, 60000]);
  });

  it("存储里是坏数据时当作没有样本，不抛错，且能覆盖写回", () => {
    localStorage.setItem(FIRST_TOKEN_SAMPLES_KEY, "{oops");
    expect(expectedFirstTokenSeconds()).toBeNull();
    recordFirstTokenMs(5000);
    expect(expectedFirstTokenSeconds()).toBe(5);
  });

  it("忽略非正数与 NaN", () => {
    recordFirstTokenMs(NaN);
    recordFirstTokenMs(-1);
    recordFirstTokenMs(0);
    expect(expectedFirstTokenSeconds()).toBeNull();
  });
});
