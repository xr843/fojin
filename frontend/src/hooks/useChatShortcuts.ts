import { useEffect, type RefObject } from "react";

/** Mac 上写 ⌘，其余写 Ctrl。模块级常量：只在加载时读一次 navigator，不在渲染期读。 */
export const MOD_KEY_LABEL =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
    ? "⌘"
    : "Ctrl";

export interface ChatShortcutOptions {
  /** 正在生成：Esc 只在此时有意义。 */
  sending: boolean;
  /** 主输入框。↑ 召回只认这个元素，/ 聚焦的也是它。 */
  inputRef: RefObject<HTMLTextAreaElement | null>;
  /** 停止生成 —— 与停止按钮同一个处理器。 */
  onStop: () => void;
  onNewChat: () => void;
  /** 上一条用户提问；没有则为 null（此时 ↑ 不拦截，保持原生行为）。 */
  lastUserText: string | null;
  onRecall: (text: string) => void;
  onToggleHelp: () => void;
}

/** 当前焦点是不是一个能打字的地方：这些元素里的 / 和 ? 是字符，不是快捷键。 */
function isEditable(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") {
    const type = (el as HTMLInputElement).type;
    return !["button", "checkbox", "radio", "submit", "reset", "range", "color", "file"].includes(type);
  }
  return el.getAttribute("role") === "textbox" || el.getAttribute("role") === "combobox";
}

/**
 * /chat 的键盘快捷键（挂在 window 上，一处收口）：
 * - Esc：生成中停止生成
 * - Ctrl/Cmd+K：新对话（生成中先停再开）
 * - ↑：输入框为空时召回上一条提问
 * - /：焦点不在可编辑元素时聚焦输入框
 * - ?：焦点不在可编辑元素时开关快捷键说明
 *
 * 输入法组字期间（isComposing 或 keyCode 229）一律放行 —— 中文输入法用 Esc 取消
 * 候选、用 ↑ 翻候选，抢走就是吞掉用户的输入。
 * 已有的 Tab 轮播与 Shift+Enter 换行不在这里处理，也不会被这里拦截。
 */
export function useChatShortcuts({
  sending, inputRef, onStop, onNewChat, lastUserText, onRecall, onToggleHelp,
}: ChatShortcutOptions): void {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.isComposing || e.keyCode === 229) return;
      if (e.defaultPrevented) return;
      const target = e.target;

      if (e.key === "Escape") {
        if (!sending) return;
        // 对话框/抽屉里的 Esc 是「关掉它」，不是「停止生成」。
        if (target instanceof Element && target.closest("[role=dialog], .ant-modal, .ant-drawer, .ant-dropdown, .ant-select-dropdown")) return;
        e.preventDefault();
        onStop();
        return;
      }

      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (sending) onStop();
        onNewChat();
        return;
      }

      if (e.ctrlKey || e.metaKey || e.altKey) return;

      if (e.key === "ArrowUp" && !e.shiftKey) {
        const input = inputRef.current;
        if (!input || target !== input || input.value !== "" || !lastUserText) return;
        e.preventDefault();
        onRecall(lastUserText);
        return;
      }

      if (isEditable(target)) return;

      if (e.key === "/") {
        const input = inputRef.current;
        if (!input) return;
        e.preventDefault();
        input.focus();
        return;
      }

      if (e.key === "?") {
        e.preventDefault();
        onToggleHelp();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [sending, inputRef, onStop, onNewChat, lastUserText, onRecall, onToggleHelp]);
}
