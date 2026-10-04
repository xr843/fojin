import { describe, it, expect } from "vitest";
import { askAiKind, buildAskAiUrl, PASSAGE_MIN_HAN } from "./searchAskAi";

describe("searchAskAi 搜索页问小津", () => {
  it("短查询当术语，长查询当经文", () => {
    expect(askAiKind("般若")).toBe("term");
    expect(askAiKind("應無所住而生其心")).toBe("passage");
    expect(askAiKind("色".repeat(PASSAGE_MIN_HAN - 1))).toBe("term");
    expect(askAiKind("色".repeat(PASSAGE_MIN_HAN))).toBe("passage");
  });

  it("标点、空格、外文不计入字数；纯外文不出按钮", () => {
    expect(askAiKind("色，空。")).toBe("term");
    expect(askAiKind("prajna paramita")).toBeNull();
    expect(askAiKind("   ")).toBeNull();
  });

  it("经文：包成 context 落地即发（不带 send，走阅读页同一条路径）", () => {
    const url = new URL(buildAskAiUrl(" 應無所住而生其心 ", "passage", "出处与意思？"), "https://x");
    expect(url.pathname).toBe("/chat");
    expect(url.searchParams.get("context")).toBe("應無所住而生其心");
    expect(url.searchParams.get("q")).toBe("出处与意思？");
    expect(url.searchParams.has("send")).toBe(false);
  });

  it("术语：send=1 落地即发（用户已点过按钮），不是裸 q", () => {
    const url = new URL(buildAskAiUrl("般若", "term", "「般若」是什么意思？"), "https://x");
    expect(url.searchParams.get("send")).toBe("1");
    expect(url.searchParams.has("context")).toBe(false);
  });
});
