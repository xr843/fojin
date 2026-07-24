import { describe, it, expect } from "vitest";
import { theme as antdTheme } from "antd";
import { buildAntdTheme } from "./antdTheme";

describe("buildAntdTheme", () => {
  it("light: default algorithm, maroon primary", () => {
    const t = buildAntdTheme(false);
    expect(t.algorithm).toBe(antdTheme.defaultAlgorithm);
    expect(t.token?.colorPrimary).toBe("#8b2500");
  });
  it("dark: dark algorithm, lightened accent, warmed neutrals", () => {
    const t = buildAntdTheme(true);
    expect(t.algorithm).toBe(antdTheme.darkAlgorithm);
    expect(t.token?.colorPrimary).toBe("#d9693c");
    expect(t.token?.colorBgBase).toBe("#2b2318");
    expect(t.token?.colorBgContainer).toBe("#3a3126");
    expect(t.token?.colorText).toBe("#ece4d6");
  });
});
