/** 思考过程片段的打字机行为。
 *
 * 使用者反馈（2026-08-13）：整块渲染的活窗「一段段文本不断地跳动」——后端按
 * 秒聚合发帧，一帧几十字整块上屏就是一跳。这里锁的是主流 LLM 界面那种效果：
 * 新到的文本进缓冲，匀速逐字吐出。
 *
 * 三条行为，第一条是本组件存在的理由：
 *   1. **不整块上屏**：一帧文本到达后的第一个 tick 只显示一部分；
 *   2. 最终追平：缓冲会被吐完，不弄丢内容；
 *   3. 文本增长（下一帧追加）时接着吐，不从头重来。
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ReasoningExcerpt from "./ReasoningExcerpt";

const FRAME = "先查《心經》的出處，再對比《大般若經》的譯例，然後決定引哪一段。";

describe("ReasoningExcerpt", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function textOf(container: HTMLElement): string {
    return container.querySelector(".chat-reasoning-excerpt-text")?.textContent ?? "";
  }

  it("一帧文本不整块上屏 —— 首个 tick 只显示一部分", () => {
    const { container } = render(<ReasoningExcerpt text={FRAME} />);
    act(() => {
      vi.advanceTimersByTime(40); // 一个 tick
    });
    const shown = textOf(container).replace("▌", "");
    expect(shown.length).toBeGreaterThan(0);
    expect(shown.length).toBeLessThan(FRAME.length);
    expect(FRAME.startsWith(shown)).toBe(true);
  });

  it("缓冲最终被吐完，内容一字不丢", () => {
    const { container } = render(<ReasoningExcerpt text={FRAME} />);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(textOf(container)).toContain(FRAME);
  });

  it("下一帧追加文本时接着吐，不从头重来", () => {
    const { container, rerender } = render(<ReasoningExcerpt text={FRAME} />);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(textOf(container)).toContain(FRAME);

    rerender(<ReasoningExcerpt text={FRAME + "另外還要核對卷號。"} />);
    act(() => {
      vi.advanceTimersByTime(40);
    });
    // 旧内容还在（没有清零重来），新内容开始逐字出现
    expect(textOf(container)).toContain(FRAME);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(textOf(container)).toContain("另外還要核對卷號。");
  });

  it("带「非最终回答」标签", () => {
    render(<ReasoningExcerpt text={FRAME} />);
    expect(screen.getByText(/非最终回答|非最終回答|not the final answer/)).toBeInTheDocument();
  });
});
