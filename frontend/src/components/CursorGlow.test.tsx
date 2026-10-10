import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import CursorGlow from "./CursorGlow";

// 跟随鼠标的光点 portal 到 body：fixed、12×12、top/left -6px。
const findGlow = () =>
  Array.from(document.body.querySelectorAll<HTMLElement>("div[aria-hidden='true']")).find(
    (el) => el.style.position === "fixed" && el.style.width === "12px",
  );

/** 让 matchMedia 只对给定的媒体查询返回 true。 */
function mockMedia(matching: string[]) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: matching.includes(query),
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CursorGlow", () => {
  it("有鼠标的桌面设备照常渲染光点", () => {
    mockMedia([]);
    render(<CursorGlow />);
    expect(findGlow()).toBeTruthy();
  });

  // 触屏没有鼠标，光点永远停在初始位置 —— 生产 390×844 实测就是左上角 (0,0)
  // 露出的半颗绿点。触屏上不应渲染任何东西。
  it("无悬停能力（hover: none）的设备不渲染光点", () => {
    mockMedia(["(hover: none)"]);
    render(<CursorGlow />);
    expect(findGlow()).toBeUndefined();
  });

  it("粗指针（pointer: coarse）的设备不渲染光点", () => {
    mockMedia(["(pointer: coarse)"]);
    render(<CursorGlow />);
    expect(findGlow()).toBeUndefined();
  });
});
