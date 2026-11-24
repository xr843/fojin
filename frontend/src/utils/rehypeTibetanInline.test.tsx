import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import Markdown from "react-markdown";
import rehypeTibetanInline from "./rehypeTibetanInline";

const html = (md: string) =>
  renderToStaticMarkup(<Markdown rehypePlugins={[rehypeTibetanInline]}>{md}</Markdown>);

describe("rehypeTibetanInline", () => {
  it("汉文里夹的藏文段包成 lang=bo 的 span，词间空格留在段内", () => {
    expect(html("译 ཅི་བཞེད་གསོལ（敬语）")).toBe(
      '<p>译 <span lang="bo" class="tz-bo-inline">ཅི་བཞེད་གསོལ</span>（敬语）</p>',
    );
    expect(html("**甲** ཀ ཁ 乙")).toContain('<span lang="bo" class="tz-bo-inline">ཀ ཁ</span> 乙');
  });

  it("引用块（整段藏文）与代码不动；没有藏文的文本不动", () => {
    expect(html("> ཀཁག")).not.toContain("tz-bo-inline");
    expect(html("`ཀཁ`")).not.toContain("tz-bo-inline");
    expect(html("纯汉文")).toBe("<p>纯汉文</p>");
  });
});
