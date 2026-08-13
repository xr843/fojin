/** 首页标题的两条一致性 —— 都是已经真实发生过漂移的地方。
 *
 * 首页标题有两个源：`index.html` 的 <title>（爬虫首屏、首次加载的 tab）与
 * locale 的 `app.title`（HomePage 的 Helmet 读它覆盖）。2026-08-13 核对时发现
 * 两处文案、以及 JSON-LD 里的站点定位，历史上各写各的。
 *
 * 更要紧的是第二条：标题说的和首页 hero 上写的曾经是两个产品 —— tab 说
 * 「佛经 AI 问答」，hero 说「全球佛教古籍数字资源聚合平台」。用户从搜索结果
 * 点进来，读到的定位对不上。修法是让标题**逐字包含** hero 标语，这条用例
 * 就是钉住它。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import zhHantTranslation from "../public/locales/zh-Hant/translation.json";
import zhTranslation from "../public/locales/zh/translation.json";

/** locale 包里并非每个值都是字符串（如 home.hot_tags 是数组），所以放宽索引
 *  签名，取值时再收窄 —— 直接 `as Record<string, string>` 会被 tsc 拒绝。 */
type Bundle = Record<string, string | string[]>;

const LOCALES: Record<"zh" | "zh-Hant", Bundle> = {
  zh: zhTranslation as Bundle,
  "zh-Hant": zhHantTranslation as Bundle,
};

const text = (loc: "zh" | "zh-Hant", key: string): string => String(LOCALES[loc][key]);

const readIndexHtml = () => readFileSync(resolve(process.cwd(), "index.html"), "utf-8");

describe("首页标题一致性", () => {
  it("index.html 的 <title> 与简体 app.title 逐字相同", () => {
    const title = /<title>([^<]*)<\/title>/.exec(readIndexHtml())?.[1];
    expect(title).toBe(text("zh", "app.title"));
  });

  it("noscript 的 <h1> 也是同一句（无脚本环境的首屏标题）", () => {
    expect(readIndexHtml()).toContain(`<h1>${text("zh", "app.title")}</h1>`);
  });

  it.each(["zh", "zh-Hant"] as const)(
    "%s: 标题包含 hero 标语 —— 站外读到的与站内看到的必须是同一个定位",
    (loc) => {
      expect(text(loc, "app.title")).toContain(text(loc, "app.tagline"));
    },
  );

  it("标题宽度在搜索结果的截断线附近仍可读（CJK 记 1、半角记 0.5）", () => {
    // Google 中文标题约显示 600px ≈ 30 全角。超一点只会截掉尾部，不是硬错误，
    // 所以这里卡的是「别再长下去」的护栏值，不是精确阈值。
    // 用码位转义而非字面字符：字符类里那个表意空格（U+3000）会被 eslint 的
    // no-irregular-whitespace 判为错误，而 CI 跑 --max-warnings 0。
    const CJK = /[\u2E80-\u9FFF\u3000-\u303F\uFF00-\uFFEF]/;
    const width = [...text("zh", "app.title")].reduce(
      (n, ch) => n + (CJK.test(ch) ? 1 : 0.5),
      0,
    );
    expect(width).toBeLessThanOrEqual(34);
  });
});
