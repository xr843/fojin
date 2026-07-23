import { describe, it, expect, beforeEach } from "vitest";
import { resolveTheme, useThemeStore } from "./themeStore";

describe("resolveTheme", () => {
  it("returns the explicit mode regardless of system pref", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
  it("follows system preference when mode is 'system'", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });
});

describe("useThemeStore", () => {
  beforeEach(() => {
    localStorage.clear();
    useThemeStore.setState({ mode: "system" });
  });
  it("defaults to system", () => {
    expect(useThemeStore.getState().mode).toBe("system");
  });
  it("setMode updates and persists under fojin-theme", () => {
    useThemeStore.getState().setMode("dark");
    expect(useThemeStore.getState().mode).toBe("dark");
    expect(JSON.parse(localStorage.getItem("fojin-theme")!).state.mode).toBe("dark");
  });
});
