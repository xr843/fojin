import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// 这些面板也渲染在 /chat 的引文抽屉里。样式若只写在随阅读页加载的 reader.css，
// 没访问过阅读页的读者看到的是无样式裸按钮——jsdom 不加载 CSS，组件测试全绿也看不出，
// 只能在这里结构性地钉住：组件用到的每个 class，都要在它自己引入的样式表里有定义。
const dir = resolve(__dirname, "..");
const CSS = readFileSync(resolve(dir, "styles/selectionExtras.css"), "utf-8");
const COMPONENTS = ["components/ReaderSelectionExtras.tsx", "components/DrawerPassageActions.tsx"];

function classNamesIn(src: string): string[] {
  const out = new Set<string>();
  for (const m of src.matchAll(/className=(?:"([^"]+)"|\{`([^`]+)`\})/g)) {
    const raw = (m[1] ?? m[2]).replace(/\$\{[^}]*\}/g, " ");
    raw.split(/\s+/).filter((c) => /^[a-z][\w-]+$/.test(c)).forEach((c) => out.add(c));
  }
  return [...out];
}

describe("selectionExtras.css 自带样式", () => {
  for (const file of COMPONENTS) {
    const src = readFileSync(resolve(dir, file), "utf-8");
    it(`${file} 自己引入 selectionExtras.css`, () => {
      expect(src).toContain('import "../styles/selectionExtras.css";');
    });
    it(`${file} 用到的 class 都在 selectionExtras.css 里定义`, () => {
      const classes = classNamesIn(src);
      expect(classes.length).toBeGreaterThan(3);
      const missing = classes.filter((c) => !new RegExp(`\\.${c}\\b`).test(CSS));
      expect(missing).toEqual([]);
    });
  }
});
