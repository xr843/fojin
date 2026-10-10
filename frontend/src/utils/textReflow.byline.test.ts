import { describe, expect, it } from "vitest";
import { reflowText } from "./textReflow";

/**
 * CBETA 把长署名硬折成两三行：「姚秦罽賓三藏佛陀耶舍 / 共竺佛念等譯」。只有末行以「譯」结尾，
 * 所以 isByline 只认出后半截，前半截被当成正文段 —— 阅读器里译者名缩进两格、墨色左对齐，
 * 与右侧的「共竺佛念等譯」拆成两处（2026-10-10 生产，四分律卷二十一）。
 * 样本取自生产 /api/texts/{id}/juans/1 的原始 content。
 */
describe("reflowText — 折行署名合并", () => {
  it("四分律卷二十一：三藏+人名 与 共…譯 合为一个署名段", () => {
    const raw = "四分律卷第二十一\n\n姚秦罽賓三藏佛陀耶舍\n共竺佛念等譯\n百眾學法之三\n\n爾時佛在舍衛國祇樹給孤獨園。時有居士\n";
    const segs = reflowText(raw);
    const bylines = segs.filter((s) => s.type === "byline");
    expect(bylines).toHaveLength(1);
    expect(bylines[0]).toMatchObject({ text: "姚秦罽賓三藏佛陀耶舍共竺佛念等譯" });
    expect(segs.some((s) => s.type === "prose" && s.text.includes("佛陀耶舍"))).toBe(false);
  });

  it("合并段的 offsets 逐字对回原文（校勘标记靠它定位）", () => {
    const raw = "四分律卷第一\n姚秦罽賓三藏佛陀耶舍\n共竺佛念等譯\n";
    const seg = reflowText(raw).find((s) => s.type === "byline");
    if (!seg || !("offsets" in seg)) throw new Error("no byline");
    expect(seg.offsets).toHaveLength(seg.text.length);
    seg.offsets.forEach((off, k) => expect(raw[off]).toBe(seg.text[k]));
  });

  it("末行不以共起头也合并（十誦律：後秦北印度三藏 / 弗若多羅共羅什譯）", () => {
    const segs = reflowText("十誦律卷第一\n後秦北印度三藏\n弗若多羅共羅什譯\n明四波羅夷法之一\n");
    expect(segs.filter((s) => s.type === "byline").map((s) => ("text" in s ? s.text : ""))).toEqual([
      "後秦北印度三藏弗若多羅共羅什譯",
    ]);
  });

  it("三行折署名（施護等奉詔譯）合为一段，且首行不被误认作经题", () => {
    const segs = reflowText(
      "三昧大教王經卷第一\n西天譯經三藏朝奉大夫試光祿卿\n傳法大師賜紫沙門臣施護等\n奉　詔譯\n金剛界大曼拏羅廣大儀軌分第一之一\n",
    );
    const bylines = segs.filter((s) => s.type === "byline");
    expect(bylines).toHaveLength(1);
    expect(bylines[0]).toMatchObject({ text: "西天譯經三藏朝奉大夫試光祿卿傳法大師賜紫沙門臣施護等奉　詔譯" });
    expect(segs.some((s) => s.type === "head")).toBe(false);
  });

  it("单行署名不受影响（金剛經）", () => {
    const segs = reflowText("金剛般若波羅蜜經\n姚秦天竺三藏鳩摩羅什譯\n\n如是我聞：\n");
    expect(segs.map((s) => s.type)).toEqual(["head", "byline", "prose"]);
  });

  it("正文里提到三藏的行不被并成署名", () => {
    // 带标点的正文行，后面紧跟一行以「譯」结尾的短句 —— 仍是正文
    const segs = reflowText("經卷第一\n\n如是我聞：\n時有三藏法師，名鳩摩羅什\n為眾宣譯\n");
    expect(segs.filter((s) => s.type === "byline").map((s) => ("text" in s ? s.text : ""))).not.toContain(
      "時有三藏法師，名鳩摩羅什為眾宣譯",
    );
    // 段落中途（前面已有正文未断段）的无标点「三藏」行也不并
    const mid = reflowText("經卷第一\n\n爾時世尊告諸比丘。彼\n三藏比丘名曰善來\n共諸弟子俱往其所譯\n");
    expect(mid.some((s) => s.type === "byline" && s.text.startsWith("三藏比丘"))).toBe(false);
  });
});
