import { create } from "zustand";

/**
 * 小津的跨组件状态。
 *
 * 为什么要个 store：隐藏状态由小津自己（HomePage 内）写，却要被页脚的
 * 「唤回小津」读——两者不在同一棵子树上。
 *
 * **一切只活在本次浏览，刻意不持久化**（2026-08-08 用户定的完整口径，与拖动
 * 位置、退出同一模式）：刷新首页永远回到默认——汉传装的通用小津。会话内
 * 选谁作答照常换装。上一版曾把 masterId/masterTradition 写盘，结果用户一打开
 * 首页看到的是上次选的印度论师装，被明确否掉（「默认的应该是汉传形象」）。
 * 存量盘里的 fojin-xiaojin 键由 XiaojinPet 挂载时清掉。
 */
interface XiaojinState {
  /**
   * 用户退出小津 —— 只管这一次浏览，刷新自动回来（2026-08-07 用户明确要求）。
   * 页脚的「唤回小津」用于不刷新就叫回来；持久退出必须成对配找回入口，否则
   * 就是那个单向门 bug（写了 localStorage 却无处恢复，用户只能开 DevTools 自救）。
   */
  hidden: boolean;
  /** 以哪位祖师的口吻作答；null = 通用助手小津。 */
  masterId: string | null;
  /** 该祖师的传承字符串（决定小津换哪套衣着）。与 masterId 同生同灭。 */
  masterTradition: string | null;
  hide: () => void;
  show: () => void;
  setMaster: (id: string | null, tradition: string | null) => void;
}

export const useXiaojinStore = create<XiaojinState>()((set) => ({
  hidden: false,
  masterId: null,
  masterTradition: null,
  hide: () => set({ hidden: true }),
  show: () => set({ hidden: false }),
  setMaster: (masterId, masterTradition) =>
    set({ masterId, masterTradition: masterId === null ? null : masterTradition }),
}));
