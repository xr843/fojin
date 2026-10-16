import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useChatShortcuts, type ChatShortcutOptions } from "./useChatShortcuts";

/** 派发一个真实的 KeyboardEvent（不走 fireEvent 的合成层），isComposing 等字段原样保留。 */
function press(target: EventTarget, init: KeyboardEventInit) {
  const ev = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(ev);
  return ev;
}

describe("useChatShortcuts", () => {
  let textarea: HTMLTextAreaElement;
  let opts: ChatShortcutOptions;

  beforeEach(() => {
    textarea = document.createElement("textarea");
    document.body.appendChild(textarea);
    opts = {
      sending: false,
      inputRef: { current: textarea },
      onStop: vi.fn(),
      onNewChat: vi.fn(),
      lastUserText: "什么是三法印？",
      onRecall: vi.fn(),
      onToggleHelp: vi.fn(),
    };
  });

  afterEach(() => {
    textarea.remove();
  });

  it("生成中按 Esc 停止；没在生成时 Esc 什么都不做", () => {
    const { rerender } = renderHook((o: ChatShortcutOptions) => useChatShortcuts(o), { initialProps: opts });
    press(document.body, { key: "Escape" });
    expect(opts.onStop).not.toHaveBeenCalled();
    rerender({ ...opts, sending: true });
    const ev = press(document.body, { key: "Escape" });
    expect(opts.onStop).toHaveBeenCalledTimes(1);
    expect(ev.defaultPrevented).toBe(true);
  });

  it("输入法组字中按 Esc / ↑ 绝不触发（isComposing 与 keyCode 229 两种信号都认）", () => {
    renderHook(() => useChatShortcuts({ ...opts, sending: true }));
    press(document.body, { key: "Escape", isComposing: true });
    press(document.body, { key: "Escape", keyCode: 229 });
    expect(opts.onStop).not.toHaveBeenCalled();
    press(textarea, { key: "ArrowUp", isComposing: true });
    expect(opts.onRecall).not.toHaveBeenCalled();
  });

  it("对话框里按 Esc 是关对话框，不停止生成", () => {
    renderHook(() => useChatShortcuts({ ...opts, sending: true }));
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    const btn = document.createElement("button");
    dialog.appendChild(btn);
    document.body.appendChild(dialog);
    press(btn, { key: "Escape" });
    expect(opts.onStop).not.toHaveBeenCalled();
    dialog.remove();
  });

  it("Ctrl+K / Cmd+K 新对话（在输入框里也生效）；生成中先停再开新对话", () => {
    const { rerender } = renderHook((o: ChatShortcutOptions) => useChatShortcuts(o), { initialProps: opts });
    const ev = press(textarea, { key: "k", ctrlKey: true });
    expect(ev.defaultPrevented).toBe(true);
    expect(opts.onNewChat).toHaveBeenCalledTimes(1);
    press(document.body, { key: "K", metaKey: true });
    expect(opts.onNewChat).toHaveBeenCalledTimes(2);
    expect(opts.onStop).not.toHaveBeenCalled();
    rerender({ ...opts, sending: true });
    press(document.body, { key: "k", ctrlKey: true });
    expect(opts.onStop).toHaveBeenCalledTimes(1);
    expect(opts.onNewChat).toHaveBeenCalledTimes(3);
    // 不带修饰键的 k 只是一个字母
    press(document.body, { key: "k" });
    expect(opts.onNewChat).toHaveBeenCalledTimes(3);
  });

  it("输入框为空时按 ↑ 召回上一条提问；有内容时 ↑ 留给光标移动", () => {
    renderHook(() => useChatShortcuts(opts));
    const ev = press(textarea, { key: "ArrowUp" });
    expect(ev.defaultPrevented).toBe(true);
    expect(opts.onRecall).toHaveBeenCalledWith("什么是三法印？");
    textarea.value = "第一行\n第二行";
    press(textarea, { key: "ArrowUp" });
    expect(opts.onRecall).toHaveBeenCalledTimes(1);
  });

  it("↑ 只在输入框里生效；没有上一条提问时不拦截", () => {
    const { rerender } = renderHook((o: ChatShortcutOptions) => useChatShortcuts(o), { initialProps: opts });
    press(document.body, { key: "ArrowUp" });
    expect(opts.onRecall).not.toHaveBeenCalled();
    rerender({ ...opts, lastUserText: null });
    const ev = press(textarea, { key: "ArrowUp" });
    expect(ev.defaultPrevented).toBe(false);
    expect(opts.onRecall).not.toHaveBeenCalled();
  });

  it("不在输入框时按 / 聚焦输入框；在任何可编辑元素里 / 照常输入", () => {
    renderHook(() => useChatShortcuts(opts));
    const ev = press(document.body, { key: "/" });
    expect(ev.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(textarea);
    textarea.blur();
    const other = document.createElement("input");
    document.body.appendChild(other);
    const ev2 = press(other, { key: "/" });
    expect(ev2.defaultPrevented).toBe(false);
    expect(document.activeElement).not.toBe(textarea);
    other.remove();
  });

  it("不在输入框时按 ? 打开快捷键说明；在输入框里 ? 是普通字符", () => {
    renderHook(() => useChatShortcuts(opts));
    press(textarea, { key: "?", shiftKey: true });
    expect(opts.onToggleHelp).not.toHaveBeenCalled();
    press(document.body, { key: "?", shiftKey: true });
    expect(opts.onToggleHelp).toHaveBeenCalledTimes(1);
  });

  it("卸载后不再响应", () => {
    const { unmount } = renderHook(() => useChatShortcuts({ ...opts, sending: true }));
    unmount();
    press(document.body, { key: "Escape" });
    expect(opts.onStop).not.toHaveBeenCalled();
  });
});
