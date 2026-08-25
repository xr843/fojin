import { readdirSync, readFileSync } from "fs";
import { resolve } from "path";
import { describe, expect, it } from "vitest";

/**
 * react-helmet-async 3.x 只接受 <title> 的**单个**子节点：写成
 * `<title>{t("x")} - {t("app.name")}</title>`（三个子节点）时它整个丢掉，页面
 * 的 <title> 变成空串 —— 生产 /dictionary 的标签页标题就是这么空的
 * （2026-08-25 Playwright 走查实测；jsdom 里同样复现）。
 *
 * 规则：每个 <title>…</title> 里最多一个 `{…}` 表达式，且表达式外不得再有文字。
 * 要拼接就用模板字符串：`<title>{`${a} - ${b}`}</title>`。
 */
const PAGES_DIR = resolve(__dirname);

function titleBodies(src: string): string[] {
  return [...src.matchAll(/<title>([\s\S]*?)<\/title>/g)].map((m) => m[1].trim());
}

/** 顶层 `{…}` 表达式个数（忽略模板字符串/嵌套花括号内部）。 */
function topLevelExpressions(body: string): { count: number; loose: string } {
  let depth = 0;
  let count = 0;
  let loose = "";
  for (const ch of body) {
    if (ch === "{") {
      if (depth === 0) count += 1;
      depth += 1;
    } else if (ch === "}") {
      depth -= 1;
    } else if (depth === 0) {
      loose += ch;
    }
  }
  return { count, loose: loose.trim() };
}

describe("<title> 只能有一个子节点（react-helmet-async 3 会丢掉数组子节点）", () => {
  const files = readdirSync(PAGES_DIR).filter((f) => f.endsWith(".tsx") && !f.includes(".test."));

  it.each(files)("%s", (file) => {
    const src = readFileSync(resolve(PAGES_DIR, file), "utf-8");
    for (const body of titleBodies(src)) {
      const { count, loose } = topLevelExpressions(body);
      const single = count <= 1 && (count === 0 || loose === "");
      expect(single, `${file}: <title>${body}</title> 有 ${count} 个表达式、松散文本 "${loose}"`).toBe(true);
    }
  });
});
