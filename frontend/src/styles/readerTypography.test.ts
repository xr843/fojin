import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, expect, it } from "vitest";

/**
 * 阅读列的行宽（measure）。2026-08-25 实测：18px 字号下正文列宽 1,374px，一行 76 个字
 * （AI 面板开着时；关掉更宽）。Sefaria / SuttaCentral / 84000 都把阅读列压在 38–45 字。
 * 42em 以正文字号为基（--reader-font-size 17–18px → 714–756px ≈ 40–42 字），居中，
 * 面板开合、字号增减时跟着变。
 */
const CSS = readFileSync(resolve(__dirname, "reader.css"), "utf-8");

function baseRule(selector: string): string {
  const i = CSS.indexOf(`\n${selector} {`);
  if (i < 0) throw new Error(`${selector} not found in reader.css`);
  return CSS.slice(i, CSS.indexOf("}", i));
}

describe("阅读列行宽", () => {
  it(".reader-body 以 em 限宽并居中（随字号缩放，不再铺满 1400px）", () => {
    const rule = baseRule(".reader-body");
    expect(rule).toMatch(/max-width:\s*42em/);
    expect(rule).toMatch(/margin(-left|-right)?:\s*(0\s+)?auto/);
  });
});
