import { describe, it, expect, beforeEach } from "vitest";
import { useXiaojinStore } from "./xiaojinStore";

describe("xiaojinStore（一切只活在本次浏览，不写盘）", () => {
  beforeEach(() => {
    localStorage.clear();
    useXiaojinStore.setState({ hidden: false, masterId: null, masterTradition: null });
  });

  it("退出、选祖师都不落 localStorage —— 刷新即回默认（汉传通用小津）", () => {
    // 上一版把祖师偏好写盘，用户打开首页看到的是上次选的印度论师装，
    // 被明确否掉（「默认的应该是汉传形象」）。谁往这个 store 加 persist，
    // 这条先红。
    useXiaojinStore.getState().hide();
    useXiaojinStore.getState().setMaster("tsongkhapa", "藏传·格鲁派");
    expect(localStorage.length).toBe(0);
  });

  it("setMaster 会话内生效（换装与口吻都靠它）", () => {
    useXiaojinStore.getState().setMaster("huineng", "禅宗");
    expect(useXiaojinStore.getState().masterId).toBe("huineng");
    expect(useXiaojinStore.getState().masterTradition).toBe("禅宗");
  });

  it("清空祖师时传承一并清空（不留孤儿传承）", () => {
    useXiaojinStore.getState().setMaster("tsongkhapa", "藏传·格鲁派");
    useXiaojinStore.getState().setMaster(null, "藏传·格鲁派");
    expect(useXiaojinStore.getState().masterTradition).toBeNull();
  });

  it("退出只在内存：hide 后 show 能叫回来（页脚「唤回小津」的路径）", () => {
    useXiaojinStore.getState().hide();
    expect(useXiaojinStore.getState().hidden).toBe(true);
    useXiaojinStore.getState().show();
    expect(useXiaojinStore.getState().hidden).toBe(false);
  });
});
