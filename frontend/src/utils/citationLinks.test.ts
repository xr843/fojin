import { describe, it, expect } from "vitest";
import { injectCitationLinks } from "./citationLinks";
import type { ChatSource } from "../api/client";

/**
 * 引文链接里的「卷号」与「段号」必须来自同一处，不能各取一半。
 *
 * 生产事故：LLM 在答案里写「【《阿毘達磨俱舍論》第16卷】」，卷号取自这句话，
 * 段号却取自检索命中的 chunk —— 而那个 chunk 属于另一卷。两个数字被拼成一对，
 * 生成「第 16 卷第 58 段」，可第 16 卷只有 0–17 段。抽屉打开后一片空白。
 *
 * 生产日志实测（近 7 天，去重后 119 个引文上下文请求）：33 个落空，落空率
 * 27.7%。且同一个段号 25 横跨卷 2/4/5/6/7/9/10/11 反复出现 —— 正是同一个
 * 检索段号被安到了 LLM 随口说出的不同卷上。
 *
 * 这类失效不报错：接口返回 200、前端无异常，只有读者点开引文看到空白。而
 * 「可核对引用」正是这个产品唯一在转的护城河。
 */

function src(o: Partial<ChatSource> = {}): ChatSource {
  return {
    text_id: 38,
    title_zh: "阿毘達磨俱舍論",
    juan_num: 9,
    chunk_index: 25,
    chunk_text: "得聖。若非定業，由得聖故，能令無果亦無驚怖",
    score: 0.9,
    ...o,
  } as ChatSource;
}

function urlOf(md: string): string | null {
  const m = md.match(/\(fojin-citation:\/\/([^)]+)\)/);
  return m ? m[1] : null;
}

describe("injectCitationLinks — 卷号与段号必须同源", () => {
  it("LLM 说的卷与检索命中的卷不一致时，不得沿用检索的段号", () => {
    // 检索命中的是第 9 卷第 25 段；LLM 却写「第 16 卷」。
    // 第 16 卷的 25 段不存在，硬拼出来只会让抽屉空白。
    const out = injectCitationLinks("见【《阿毘達磨俱舍論》第16卷】所说。", [src()]);
    const url = urlOf(out);
    expect(url).not.toBeNull();
    const [, juan, chunk] = url!.split("/");
    expect(juan).toBe("16");
    expect(chunk).toBe("-1"); // -1 → 点击时退回该卷阅读器，那是真实存在的
  });

  it("两者一致时保留段号，读者仍能精确落到被引段落", () => {
    const out = injectCitationLinks("见【《阿毘達磨俱舍論》第9卷】所说。", [src()]);
    const [, juan, chunk] = urlOf(out)!.split("/");
    expect(juan).toBe("9");
    expect(chunk).toBe("25");
  });

  it("LLM 未写卷号时沿用检索结果自身的卷与段，两者本就同源", () => {
    const out = injectCitationLinks("见【《阿毘達磨俱舍論》】所说。", [src()]);
    const [, juan, chunk] = urlOf(out)!.split("/");
    expect(juan).toBe("9");
    expect(chunk).toBe("25");
  });

  it("多个候选中若某段确实含引文，锚到那一段，卷号随之改写", () => {
    // 引文须 ≥6 字：extractPrecedingQuote 的正则下限就是 6，
    // pickSourceForQuote 归一化后也要求 ≥6。用 5 字的「無學身語業」
    // 会静默抽取失败、锚定不触发，用例便测不到它想测的东西。
    const out = injectCitationLinks(
      "论云「無學身語業，即意三牟尼」者。【《阿毘達磨俱舍論》第2卷】",
      [
        src({ juan_num: 9, chunk_index: 25, score: 0.95 }),
        src({ juan_num: 16, chunk_index: 7, score: 0.5, chunk_text: "無學身語業，即意三牟尼" }),
      ],
    );
    const url = urlOf(out);
    expect(url).not.toBeNull();
    const [, juan, chunk] = url!.split("/");
    // 引文命中的那一段来自第 16 卷 —— 卷段同源，段号有效。
    // 这里必须硬断言：包一层 `if (chunk !== "-1")` 会让退化成 -1 时整条用例
    // 空转通过，而它守的恰恰是「引文命中哪段就锚哪段」这个最关键的行为。
    expect(juan).toBe("16");
    expect(chunk).toBe("7");
  });
});

/**
 * CBETA 的 title_zh 恒为繁体，而答案正文是 LLM 写的简体。两者并排出现在同一句话里
 * ——生产实测：简体界面下答案写「色不异空」，紧跟的引文标记却是
 * 【《般若波羅蜜多心經》第1卷】，而点开后抽屉标题又是简体的《般若波罗蜜多心经》。
 * 同一部经在一屏内出现两种字形，直接削弱「这是同一段原文」的可信度，而可核对引用
 * 正是这个产品唯一在转的护城河。
 *
 * 修法与 CollectionsPage / CrossCanonPage 一致：localizeHan(text, language)。
 * 只动**经名**，绝不动答案正文——被逐字核验过的引文一个字都不能改写。
 */
describe("injectCitationLinks — 可见经名跟随界面语言", () => {
  it("简体界面：把 CBETA 繁体经名折成简体", () => {
    const out = injectCitationLinks("见【《阿毘達磨俱舍論》第9卷】所说。", [src()], "zh");
    expect(out).toContain("【《阿毘达磨俱舍论》第9卷】");
  });

  it("繁体界面：保持繁体，不被折成简体", () => {
    const out = injectCitationLinks("见【《阿毘達磨俱舍論》第9卷】所说。", [src()], "zh-Hant");
    expect(out).toContain("【《阿毘達磨俱舍論》第9卷】");
  });

  it("裸经名（无【】标记的第二遍扫描）同样跟随界面语言", () => {
    const out = injectCitationLinks("《阿毘達磨俱舍論》里说。", [src()], "zh");
    expect(out).toContain("[《阿毘达磨俱舍论》]");
  });

  it("只折经名，不碰答案正文里被引的经句", () => {
    // 承重。「無學身語業，即意三牟尼」是通过了逐字核验的引文，界面语言不是
    // 改写它的理由——一旦这里也转字，「已逐字核验」这个徽章当场就变成假话。
    const out = injectCitationLinks(
      "论云「無學身語業，即意三牟尼」者。【《阿毘達磨俱舍論》第9卷】",
      [src()],
      "zh",
    );
    expect(out).toContain("「無學身語業，即意三牟尼」");
    expect(out).toContain("《阿毘达磨俱舍论》");
  });

  it("URL 里的标题仍是简体，与界面语言无关（抽屉靠它做键匹配）", () => {
    const out = injectCitationLinks("见【《阿毘達磨俱舍論》第9卷】所说。", [src()], "zh-Hant");
    expect(urlOf(out)).toContain(encodeURIComponent("阿毘达磨俱舍论"));
  });
});
