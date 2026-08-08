import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * 小津的跨组件偏好。
 *
 * 为什么要个 store：隐藏状态由小津自己（HomePage 内）写，却要被页脚的
 * 「唤回小津」读——两者不在同一棵子树上。持久退出必须**成对**配一个找回
 * 入口，否则就是 2026-08-07 那个单向门 bug（写了 localStorage 却无处恢复，
 * 用户只能开 DevTools 自救）。ryOS 的「退出助理」敢做持久，也是因为它有
 * 控制面板做找回入口。
 */
interface XiaojinState {
  /**
   * 用户退出小津 —— **只管这一次浏览，刷新自动回来**（不持久化，见下方
   * partialize/merge）。用户 2026-08-07 明确要求：按了退出，下次刷新页面
   * 仍要自动弹出小津。页脚的「唤回小津」用于不刷新就叫回来。
   */
  hidden: boolean;
  /** 以哪位祖师的口吻作答；null = 通用助手小津。持久。 */
  masterId: string | null;
  /** 该祖师的传承字符串（决定小津换哪套衣着）。与 masterId 同生同灭，持久。 */
  masterTradition: string | null;
  hide: () => void;
  show: () => void;
  setMaster: (id: string | null, tradition: string | null) => void;
}

export const useXiaojinStore = create<XiaojinState>()(
  persist(
    (set) => ({
      hidden: false,
      masterId: null,
      masterTradition: null,
      hide: () => set({ hidden: true }),
      show: () => set({ hidden: false }),
      setMaster: (masterId, masterTradition) =>
        set({ masterId, masterTradition: masterId === null ? null : masterTradition }),
    }),
    {
      name: "fojin-xiaojin",
      // 只持久化祖师偏好。hidden 刻意不写盘 —— 刷新必须让小津回来。
      partialize: (s) => ({ masterId: s.masterId, masterTradition: s.masterTradition }),
      // merge 里强制 hidden:false：光靠 partialize 不够 —— 存量用户的
      // localStorage 里还留着上一版写进去的 hidden:true，默认 merge 会把它
      // 灌回来，小津照样不出现。
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as Partial<XiaojinState>),
        hidden: false,
      }),
    },
  ),
);
