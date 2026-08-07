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
  /** 用户主动退出小津。持久；靠页脚的「唤回小津」恢复。 */
  hidden: boolean;
  /** 以哪位祖师的口吻作答；null = 通用助手小津。持久。 */
  masterId: string | null;
  hide: () => void;
  show: () => void;
  setMasterId: (id: string | null) => void;
}

export const useXiaojinStore = create<XiaojinState>()(
  persist(
    (set) => ({
      hidden: false,
      masterId: null,
      hide: () => set({ hidden: true }),
      show: () => set({ hidden: false }),
      setMasterId: (masterId) => set({ masterId }),
    }),
    { name: "fojin-xiaojin" },
  ),
);
