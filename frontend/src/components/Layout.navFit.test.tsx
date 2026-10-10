import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import Layout from "./Layout";

/*
 * 顶栏导航「放得下才展开，放不下就收成汉堡」。
 *
 * 展开所需宽度随语言、角色、用户名而变（2026-10-10 实测：中文游客 1002px、
 * 中文登录 1057px、英文游客 1254px、英文管理员 ≈1470px），任何一个写死的
 * 断点都会让某种组合横向溢出，所以按实际宽度判。jsdom 没有排版，这里把
 * 几个参与计算的元素的宽度桩成固定值，只验证「判据 + 跟随尺寸变化」这层逻辑；
 * 真实宽度下的溢出由 Playwright 逐宽度扫描（见 PR 描述）。
 */

const size = { header: 1440, logo: 52, nav: 953, actions: 300 };

const clientWidthDesc = Object.getOwnPropertyDescriptor(Element.prototype, "clientWidth");
const offsetWidthDesc = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetWidth");
const RealResizeObserver = globalThis.ResizeObserver;
let roCallbacks: Array<() => void> = [];

beforeEach(() => {
  size.header = 1440;
  roCallbacks = [];
  Object.defineProperty(Element.prototype, "clientWidth", {
    configurable: true,
    get(this: Element) {
      return this.classList.contains("ant-layout-header") ? size.header : 0;
    },
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get(this: HTMLElement) {
      if (this.classList.contains("nav-desktop")) return size.nav;
      if (this.classList.contains("header-logo")) return size.logo;
      if (this.classList.contains("header-actions")) return size.actions;
      return 0;
    },
  });
  globalThis.ResizeObserver = class {
    private cb: () => void;
    constructor(cb: () => void) {
      this.cb = cb;
      roCallbacks.push(cb);
    }
    observe() {}
    unobserve() {}
    disconnect() {
      roCallbacks = roCallbacks.filter((c) => c !== this.cb);
    }
  } as unknown as typeof ResizeObserver;
});

afterEach(() => {
  if (clientWidthDesc) Object.defineProperty(Element.prototype, "clientWidth", clientWidthDesc);
  if (offsetWidthDesc) Object.defineProperty(HTMLElement.prototype, "offsetWidth", offsetWidthDesc);
  globalThis.ResizeObserver = RealResizeObserver;
});

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/chat"]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="*" element={<div />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const navSlot = (c: HTMLElement) => c.querySelector(".header-nav") as HTMLElement;

describe("顶栏导航按实际宽度收起", () => {
  it("放得下（1440 宽）时整排展开，不收成汉堡", () => {
    const { container } = renderLayout();
    expect(navSlot(container)).not.toBeNull();
    expect(navSlot(container).classList.contains("is-collapsed")).toBe(false);
  });

  it("放不下（900 宽，导航本身就要 953）时收成汉堡", () => {
    size.header = 900;
    const { container } = renderLayout();
    expect(navSlot(container).classList.contains("is-collapsed")).toBe(true);
  });

  it("窗口缩放跨过所需宽度时跟着切换，来回都对", () => {
    const { container } = renderLayout();
    expect(navSlot(container).classList.contains("is-collapsed")).toBe(false);

    size.header = 1000;
    act(() => roCallbacks.forEach((cb) => cb()));
    expect(navSlot(container).classList.contains("is-collapsed")).toBe(true);

    size.header = 1600;
    act(() => roCallbacks.forEach((cb) => cb()));
    expect(navSlot(container).classList.contains("is-collapsed")).toBe(false);
  });

  it("收起后仍按导航的自然宽度判（收起本身不能让它「看起来放得下」而来回抖）", () => {
    size.header = 1300;
    size.nav = 1200;
    const { container } = renderLayout();
    expect(navSlot(container).classList.contains("is-collapsed")).toBe(true);
    // 再触发几次测量：结果必须稳定，不能在展开/收起之间翻转
    act(() => roCallbacks.forEach((cb) => cb()));
    act(() => roCallbacks.forEach((cb) => cb()));
    expect(navSlot(container).classList.contains("is-collapsed")).toBe(true);
    size.nav = 953;
  });

  it("拿不到排版信息（宽度为 0）时保持展开，交给 ≤768px 的 CSS 兜底", () => {
    size.header = 0;
    const { container } = renderLayout();
    expect(navSlot(container).classList.contains("is-collapsed")).toBe(false);
  });
});
