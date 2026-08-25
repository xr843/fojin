import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, expect, it } from "vitest";

/**
 * 页面「铬」（顶栏 / 页脚 / 内容区上下内边距）的高度必须是共享 token，而不是散落在
 * Layout 内联样式与各页 calc() 里的裸数字。
 *
 * 2026-08-25 生产实锤：/chat 的外壳写死 `calc(100vh - 120px)`，而实际是
 * 顶栏 52 + 内容区上下 24×2 + 页脚 50 = 150 —— 文档比视口高 30px，发送后自动贴底
 * 把导航栏整个滚出视口，每次对话都能看到半截图标。数字分居两处就一定会漂。
 */

const CSS = readFileSync(resolve(__dirname, "global.css"), "utf-8");

function rootBlock(): string {
  const m = CSS.match(/:root\s*\{([\s\S]*?)\n\}/);
  if (!m) throw new Error(":root block not found");
  return m[1];
}

function rule(selector: string): string {
  // 取该选择器在文件里的**第一条**声明块（基础值；媒体查询里的覆盖另测）。
  const idx = CSS.indexOf(`\n${selector} {`);
  if (idx < 0) throw new Error(`rule ${selector} not found in global.css`);
  const end = CSS.indexOf("}", idx);
  return CSS.slice(idx, end);
}

describe("布局铬高度 token", () => {
  it(":root 定义顶栏/页脚/内容区内边距三个 token", () => {
    const root = rootBlock();
    expect(root).toMatch(/--fj-header-h:\s*52px/);
    expect(root).toMatch(/--fj-footer-h:\s*50px/);
    expect(root).toMatch(/--fj-content-pad-y:\s*24px/);
  });

  it("内容区内边距吃 token，而不是再写一遍 24px", () => {
    expect(rule(".layout-content-inner")).toMatch(/padding:\s*var\(--fj-content-pad-y\)/);
  });

  it("移动端把内容区内边距 token 改成 12px（与原来的 12px 10px 一致）", () => {
    const mobile = CSS.match(/@media \(max-width: 768px\)\s*\{[\s\S]*?--fj-content-pad-y:\s*(\d+)px/);
    expect(mobile?.[1]).toBe("12");
  });

  it("对话外壳高度用三个 token 算，且给 100dvh 一份（手机地址栏收放不再溢出）", () => {
    const shell = rule(".chat-shell");
    expect(shell).toMatch(
      /height:\s*calc\(100vh - var\(--fj-header-h\) - var\(--fj-footer-h\) - 2 \* var\(--fj-content-pad-y\)\)/,
    );
    expect(shell).toMatch(
      /height:\s*calc\(100dvh - var\(--fj-header-h\) - var\(--fj-footer-h\) - 2 \* var\(--fj-content-pad-y\)\)/,
    );
    expect(shell).not.toMatch(/120px/);
  });

  it("手机空态放开外壳高度（height:auto），有对话后才锁高钉底", () => {
    const m = CSS.match(/@media \(max-width: 768px\)\s*\{[\s\S]*?\.chat-shell\.chat-shell--empty\s*\{([^}]*)\}/);
    expect(m, ".chat-shell.chat-shell--empty rule missing from the ≤768px block").not.toBeNull();
    expect(m![1]).toMatch(/height:\s*auto/);
    expect(m![1]).toMatch(/min-height:\s*calc\(100dvh - var\(--fj-header-h\)/);
  });
});
