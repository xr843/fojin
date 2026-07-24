import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useApplyTheme } from "./useTheme";
import { useThemeStore } from "../stores/themeStore";

// jsdom has no real matchMedia — provide a controllable mock.
function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe("useApplyTheme", () => {
  beforeEach(() => {
    localStorage.clear();
    useThemeStore.setState({ mode: "system" });
    document.documentElement.removeAttribute("data-theme");
    if (!document.querySelector('meta[name="theme-color"]')) {
      const m = document.createElement("meta");
      m.setAttribute("name", "theme-color");
      document.head.appendChild(m);
    }
  });

  it("system + OS dark → data-theme=dark and dark meta color", () => {
    mockMatchMedia(true);
    renderHook(() => useApplyTheme());
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.querySelector('meta[name="theme-color"]')!.getAttribute("content")).toBe("#221c14");
  });

  it("explicit light beats OS dark", () => {
    mockMatchMedia(true);
    useThemeStore.setState({ mode: "light" });
    renderHook(() => useApplyTheme());
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.querySelector('meta[name="theme-color"]')!.getAttribute("content")).toBe("#8b2500");
  });
});
