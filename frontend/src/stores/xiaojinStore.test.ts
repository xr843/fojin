import { describe, it, expect, beforeEach } from "vitest";
import { useXiaojinStore } from "./xiaojinStore";

const KEY = "fojin-xiaojin";

/** 让 persist 中间件按当前 localStorage 重新水合一次（等价于刷新页面）。 */
async function rehydrate() {
  await useXiaojinStore.persist.rehydrate();
}

describe("xiaojinStore 持久化边界", () => {
  beforeEach(() => {
    localStorage.clear();
    useXiaojinStore.setState({ hidden: false, masterId: null, masterTradition: null });
  });

  it("退出不写盘：hidden 只活在内存里", () => {
    useXiaojinStore.getState().hide();
    expect(useXiaojinStore.getState().hidden).toBe(true);

    const persisted = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    // 写进盘就意味着刷新后小津还是不出现——用户明确要求刷新要自动弹出
    expect(persisted.state?.hidden).toBeUndefined();
  });

  it("祖师偏好照常写盘（含传承——决定换哪套衣着）", () => {
    useXiaojinStore.getState().setMaster("huineng", "禅宗");
    const persisted = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    expect(persisted.state?.masterId).toBe("huineng");
    expect(persisted.state?.masterTradition).toBe("禅宗");
  });

  it("清空祖师时传承一并清空（不留孤儿传承）", () => {
    useXiaojinStore.getState().setMaster("tsongkhapa", "藏传·格鲁派");
    useXiaojinStore.getState().setMaster(null, "藏传·格鲁派");
    expect(useXiaojinStore.getState().masterTradition).toBeNull();
  });

  it("存量用户盘里残留的 hidden:true 在水合时被强制清掉", async () => {
    // 上一版（#1142）把 hidden 也写进了盘。只做 partialize 不够：默认 merge
    // 会把这个残留灌回内存，小津照样不出现——必须在 merge 里强制 false。
    localStorage.setItem(
      KEY,
      JSON.stringify({ state: { hidden: true, masterId: "xuanzang" }, version: 0 }),
    );
    await rehydrate();

    expect(useXiaojinStore.getState().hidden).toBe(false);
    // 祖师偏好不能跟着一起丢
    expect(useXiaojinStore.getState().masterId).toBe("xuanzang");
  });

  it("退出后水合一次（＝刷新）小津就回来", async () => {
    useXiaojinStore.getState().hide();
    expect(useXiaojinStore.getState().hidden).toBe(true);
    await rehydrate();
    expect(useXiaojinStore.getState().hidden).toBe(false);
  });
});
