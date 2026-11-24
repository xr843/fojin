import { describe, expect, it } from "vitest";
import { noteId, parseTzHref, prepareDocument, refId } from "./tibetanZhDoc";

const SIMPLE = [
  "# 书名",
  "",
  "## 解题",
  "",
  "说明〔校注 1〕。",
  "",
  "## 正文",
  "",
  "> བོད་སྐད་དུ།",
  "",
  "汉译〔校注 2〕，又〔校注 1〕，又〔校注 9〕。",
  "",
  "```",
  "〔校注 1〕 代码块里不改",
  "```",
  "",
  "## 校注",
  "",
  "1. 第一条，参见〔校注 2〕。",
  "2. 第二条。",
  "",
  "## 自查",
  "",
  "见〔校注 2〕。",
].join("\n");

describe("prepareDocument", () => {
  it("每个「## 」开新块，目录以「## 」为单位", () => {
    const doc = prepareDocument(SIMPLE);
    expect(doc.toc.map((e) => e.title)).toEqual(["解题", "正文", "校注", "自查"]);
    for (const e of doc.toc) expect(doc.chunks[e.chunk].text.startsWith("## ")).toBe(true);
    expect(doc.chunks.map((c) => c.text).join("\n")).toContain("> བོད་སྐད་དུ།");
  });

  it("正文标记改写成指向校注的链接，校注条目带跳回锚点", () => {
    const doc = prepareDocument(SIMPLE);
    const all = doc.chunks.map((c) => c.text).join("\n");
    expect(all).toContain("说明[〔校注 1〕](#tzref-0-1-0)");
    expect(all).toContain("1. [↩](#tzback-0-1) 第一条");
    expect(all).toContain("2. [↩](#tzback-0-2) 第二条");
    // 校注节里的互引、校注节之后的引用都指向这一节
    expect(all).toMatch(/参见\[〔校注 2〕\]\(#tzref-0-2-\d+\)/);
    expect(all).toMatch(/见\[〔校注 2〕\]\(#tzref-0-2-\d+\)/);
    // 没有对应条目的标记保持原文
    expect(all).toContain("又〔校注 9〕");
    // 代码块里不动
    expect(all).toContain("〔校注 1〕 代码块里不改");
    // 锚点 → 所在块
    const notesChunk = doc.toc.find((e) => e.title === "校注")!.chunk;
    expect(doc.anchorChunk.get(noteId(0, 1))).toBe(notesChunk);
    expect(doc.anchorChunk.get(refId(0, 1, 0))).toBe(doc.toc[0].chunk);
    expect(doc.firstRefOf.get(noteId(0, 1))).toBe(refId(0, 1, 0));
  });

  it("分段各有校注、编号各自从 1 起时（T-2978 式），标记指向本段的校注", () => {
    const md = [
      "## 第 1 段",
      "甲〔校注 1〕",
      "### 第1段·校注",
      "1. 一段一",
      "### 异文表",
      "| a | 〔校注 1〕 |",
      "|---|---|",
      "## 第 2 段",
      "乙〔校注 1〕",
      "### 第2段·校注",
      "1. 二段一",
    ].join("\n");
    const all = prepareDocument(md).chunks.map((c) => c.text).join("\n");
    expect(all).toMatch(/甲\[〔校注 1〕\]\(#tzref-0-1-\d+\)/);
    expect(all).toMatch(/\| a \| \[〔校注 1〕\]\(#tzref-0-1-\d+\) \|/); // 段末表格引用本段（前面那节）
    expect(all).toMatch(/乙\[〔校注 1〕\]\(#tzref-1-1-\d+\)/);
    expect(all).toContain("1. [↩](#tzback-1-1) 二段一");
  });

  it("没有校注节时原文不动", () => {
    const md = "## 甲\n\n正文〔校注 1〕。";
    expect(prepareDocument(md).chunks.map((c) => c.text).join("\n")).toBe(md);
  });

  it("大节按体积切细：标题、空行、校注条目处切，每块不超过上限太多", () => {
    const para = "汉".repeat(400);
    const body: string[] = ["## 大节"];
    for (let i = 1; i <= 300; i++) body.push("", `##### 〔${i}〕`, "", para);
    body.push("", "## 校注", "");
    for (let i = 1; i <= 300; i++) body.push(`${i}. ${para}`);
    const doc = prepareDocument(body.join("\n"));
    expect(doc.chunks.length).toBeGreaterThan(10);
    for (const c of doc.chunks) expect(c.text.length).toBeLessThan(18_000);
    // 校注列表从中间切开时，新块以条目开头（渲染为 <ol start=N>，编号不乱）
    const noteChunks = doc.chunks.filter((c) => c.index > doc.toc[1].chunk);
    expect(noteChunks.length).toBeGreaterThan(0);
    for (const c of noteChunks) expect(c.text).toMatch(/^\d+\. /);
    // 拼回去与改写后的全文一致（切块不丢行）
    expect(doc.chunks.map((c) => c.text).join("\n").split("\n")).toHaveLength(body.length);
  });

  it("估计高度：只看汉文时不计藏文引用块", () => {
    const doc = prepareDocument("## 甲\n\n> " + "ཀ".repeat(200) + "\n\n汉文");
    expect(doc.chunks[0].estHeightZhOnly).toBeLessThan(doc.chunks[0].estHeight);
  });
});

describe("parseTzHref", () => {
  it("只认改写出来的两种站内锚点", () => {
    expect(parseTzHref("#tzref-1-23-4")).toEqual({ kind: "ref", section: 1, n: 23, k: 4 });
    expect(parseTzHref("#tzback-0-7")).toEqual({ kind: "back", section: 0, n: 7 });
    expect(parseTzHref("https://example.com/#tzref-1-2-3")).toBeNull();
    expect(parseTzHref(undefined)).toBeNull();
  });
});
