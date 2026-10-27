import { render } from "@testing-library/react";
import Markdown from "react-markdown";
import { describe, expect, it } from "vitest";
import { MARKDOWN_REMARK_PLUGINS } from "./markdownPlugins";

function html(md: string): string {
  return render(<Markdown remarkPlugins={MARKDOWN_REMARK_PLUGINS}>{md}</Markdown>).container.innerHTML;
}

describe("MARKDOWN_REMARK_PLUGINS", () => {
  // 生产会话 3654 原文：收尾的 ** 前是「。」后紧跟汉字，CommonMark 不认作结束，页面露出星号。
  it("closes bold after CJK punctuation followed by a Han character", () => {
    const out = html("第一，**修行不是「造作」出一个佛性，而是「显了」本具的清净。**如来藏自性清净。");
    expect(out).toContain("<strong>修行不是「造作」出一个佛性，而是「显了」本具的清净。</strong>");
    expect(out).not.toContain("**");
  });

  it("opens bold right before a CJK opening bracket", () => {
    const out = html("经中说**「一切法空」**是根本。");
    expect(out).toContain("<strong>「一切法空」</strong>");
  });

  it("leaves citation markers and GFM tables intact", () => {
    const out = html("见【《金剛般若波羅蜜經》第1卷】。\n\n| a | b |\n|---|---|\n| 1 | 2 |");
    expect(out).toContain("【《金剛般若波羅蜜經》第1卷】");
    expect(out).toContain("<table>");
  });
});

describe("GFM 裸网址遇到中文就结束", () => {
  // 用户截图（2026-10-27）：「（https://rywiki.tsadra.org/）和 Sacred…」整串成了一个链接，
  // href 带着「）和」，点开 404。GFM 只在空白处结束裸网址，中文行文里网址后面不留空格。
  // 生产 180 天：AI 回答里 850 个网址有 778 个（91.5%）这样被吞，紧跟的都是全角「）」。
  const hrefs = (md: string) => [...render(<Markdown remarkPlugins={MARKDOWN_REMARK_PLUGINS}>{md}</Markdown>).container.querySelectorAll("a")].map((a) => [a.getAttribute("href"), a.textContent]);

  it("stops at a full-width closing paren and keeps the following text as prose", () => {
    const md = "可以访问让炯耶谢维基（https://rywiki.tsadra.org/）和 Sacred Texts 佛教文献（https://sacred-texts.com/bud/index.htm）自行检索更广泛的佛典资料。";
    expect(hrefs(md)).toEqual([
      ["https://rywiki.tsadra.org/", "https://rywiki.tsadra.org/"],
      ["https://sacred-texts.com/bud/index.htm", "https://sacred-texts.com/bud/index.htm"],
    ]);
    expect(html(md)).toContain("</a>）和 Sacred Texts 佛教文献（");
    expect(html(md)).toContain("</a>）自行检索更广泛的佛典资料。");
  });

  it("still links a second URL that was swallowed into the first one's tail", () => {
    expect(hrefs("见https://a.org/x，以及https://b.org/y。")).toEqual([
      ["https://a.org/x", "https://a.org/x"],
      ["https://b.org/y", "https://b.org/y"],
    ]);
  });

  it("stops at a Han character with no punctuation in between", () => {
    expect(hrefs("参见 https://cbetaonline.dila.edu.tw/zh/T0235和其他版本")).toEqual([
      ["https://cbetaonline.dila.edu.tw/zh/T0235", "https://cbetaonline.dila.edu.tw/zh/T0235"],
    ]);
  });

  it("leaves explicit markdown links and plain ASCII autolinks untouched", () => {
    expect(hrefs("[CBETA 中文](https://cbeta.org/中文页) 与 https://suttacentral.net/mn1 。")).toEqual([
      ["https://cbeta.org/%E4%B8%AD%E6%96%87%E9%A1%B5", "CBETA 中文"], // 显式链接原样保留（react-markdown 负责百分号编码）
      ["https://suttacentral.net/mn1", "https://suttacentral.net/mn1"],
    ]);
  });
});
