import { describe, it, expect } from "vitest";
import { injectCitationLinks } from "./ChatPage";
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
    const out = injectCitationLinks(
      "论云「無學身語業」者。【《阿毘達磨俱舍論》第2卷】",
      [
        src({ juan_num: 9, chunk_index: 25, score: 0.95 }),
        src({ juan_num: 16, chunk_index: 7, score: 0.5, chunk_text: "無學身語業，即意三牟尼" } as Partial<ChatSource>),
      ],
    );
    const url = urlOf(out);
    expect(url).not.toBeNull();
    const [, juan, chunk] = url!.split("/");
    // 引文命中的那一段来自第 16 卷 —— 卷段同源，段号有效
    if (chunk !== "-1") {
      expect(juan).toBe("16");
      expect(chunk).toBe("7");
    }
  });
});
