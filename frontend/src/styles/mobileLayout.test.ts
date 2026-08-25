import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, expect, it } from "vitest";

/**
 * 两处手机布局坏点（2026-08-25 Playwright 390px 生产实测）：
 *
 * /sources：`.sources-grid` 在 ≤768px 只写了 `1fr`，而 `1fr` = `minmax(auto, 1fr)`，
 *   轨道的最小值是卡片的 min-content —— `.source-card-top` 是 nowrap 的 flex 行，
 *   英文名一整行不折，min-content 算到 504px，于是单列轨道被撑到 504.6px、卡片 505px、
 *   布局视口撑到 608px，描述文字在屏幕右缘被裁。要 `minmax(0, 1fr)`。
 *
 * /kg：≤768px 里 `.kg-toolbar-main .ant-input-search { flex: 1; min-width: 0 }`
 *   让搜索框跟「全部类型」(110px) 与「深度」(120px) 同排挤在一行，只剩 86px，
 *   减去搜索按钮后输入框 1px 宽。要占满整行（flex-basis 100%），让另外两个换行。
 */

const SOURCES = readFileSync(resolve(__dirname, "sources.css"), "utf-8");
const KG = readFileSync(resolve(__dirname, "kg.css"), "utf-8");

/** 取某个 max-width 媒体块里某选择器的声明体（第一处）。 */
function ruleInMedia(css: string, maxWidth: number, selector: string): string {
  const re = new RegExp(`@media \\(max-width: ${maxWidth}px\\)\\s*\\{([\\s\\S]*?)\\n\\}`, "g");
  for (const m of css.matchAll(re)) {
    const block = m[1];
    const i = block.indexOf(`${selector} {`);
    if (i >= 0) return block.slice(i, block.indexOf("}", i));
  }
  throw new Error(`${selector} not found in any @media (max-width: ${maxWidth}px) block`);
}

function baseRule(css: string, selector: string): string {
  const i = css.indexOf(`\n${selector} {`);
  if (i < 0) throw new Error(`${selector} not found`);
  return css.slice(i, css.indexOf("}", i));
}

describe("手机布局：/sources 网格与 /kg 工具栏", () => {
  it("/sources 单列轨道最小值必须是 0，不能让卡片的 min-content 撑宽视口", () => {
    expect(ruleInMedia(SOURCES, 768, ".sources-grid")).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  });

  it("/sources 桌面网格的列宽下限不得超过容器（min(320px, 100%)）", () => {
    expect(baseRule(SOURCES, ".sources-grid")).toMatch(/minmax\(min\(320px,\s*100%\),\s*1fr\)/);
  });

  it("/kg 手机上搜索框独占一行（flex-basis 100%），不与类型/深度同排挤压", () => {
    const rule = ruleInMedia(KG, 768, ".kg-toolbar-main .ant-input-search");
    expect(rule).toMatch(/flex:\s*1 1 100%/);
    expect(rule).toMatch(/min-width:\s*0/);
  });
});
