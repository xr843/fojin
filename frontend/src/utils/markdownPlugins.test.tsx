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
