import { describe, expect, it } from "vitest";
import { reflowText, type TextSegment } from "./textReflow";

/**
 * 经题折行与品题识别。样本取自生产 /api/texts/{id}/juans/{n} 的原始 content（2026-10-10）。
 * CBETA 把长经题硬折成两行，只有一半被认作标题，另一半落进正文；卷首品题（「百眾學法之三」）
 * 没有「品第」字样，被并进正文首段。回放基准与误伤核查见 PR 描述。
 */
type Texty = Extract<TextSegment, { text: string }>;
const typed = (segs: TextSegment[]) => segs.map((s) => (s.type === "break" ? "break" : `${s.type}:${(s as Texty).text}`));

/** 所有带字片段的 offsets 必须逐字对回原文、严格递增 —— 划词、校勘标记、行锚都靠它。 */
function expectOffsetsExact(raw: string, segs: TextSegment[]) {
  let prev = -1;
  for (const s of segs) {
    if (s.type === "break") continue;
    expect(s.offsets).toHaveLength(s.text.length);
    s.offsets.forEach((o, k) => {
      expect(raw[o]).toBe(s.text[k]);
      expect(o).toBeGreaterThan(prev);
      prev = o;
    });
  }
}

describe("reflowText — 经题折行", () => {
  it("大智度論卷一：「…釋論 / 第一」合为一个经题，「第一」不进正文", () => {
    const raw = "大智度初序品中緣起義釋論\n第一\n龍樹菩薩造\n後秦龜茲國三藏法師鳩摩羅什\n奉　詔譯\n智度大道佛從來，智度大海佛窮盡，\n";
    const segs = reflowText(raw);
    expect(typed(segs).slice(0, 3)).toEqual([
      "head:大智度初序品中緣起義釋論第一",
      "byline:龍樹菩薩造",
      "byline:後秦龜茲國三藏法師鳩摩羅什奉　詔譯",
    ]);
    expectOffsetsExact(raw, segs);
  });

  it("大智度論卷三十四：后半截带前缀（世界義第五十一之餘）也并回经题", () => {
    const raw = "大智度論釋初品中見一切佛\n世界義第五十一之餘\n聖者龍樹造\n後秦龜茲國三藏鳩摩羅什譯\n\n【經】\n";
    const segs = reflowText(raw);
    expect(typed(segs)[0]).toBe("head:大智度論釋初品中見一切佛世界義第五十一之餘");
    expect(segs.some((s) => s.type === "prose" && s.text.includes("世界義"))).toBe(false);
    expectOffsetsExact(raw, segs);
  });

  it("大日經卷一：「…經卷 / 第一」合为卷题，随后的两行署名因此能合上", () => {
    const raw = "大毘盧遮那成佛神變加持經卷\n第一\n大唐天竺三藏善無畏\n共沙門一行譯\n入真言門住心品第一\n\n如是我聞：\n";
    const segs = reflowText(raw);
    expect(typed(segs)).toEqual([
      "juan:大毘盧遮那成佛神變加持經卷第一",
      "byline:大唐天竺三藏善無畏共沙門一行譯",
      "section:入真言門住心品第一",
      "prose:如是我聞：",
    ]);
    expectOffsetsExact(raw, segs);
  });

  it("大日經卷二：卷题与署名之间隔空行也成立", () => {
    const segs = reflowText("大毘盧遮那成佛神變加持經卷\n第二\n\n大唐天竺三藏善無畏\n共沙門一行譯\n入漫茶羅具緣真言品第二之餘\n\n爾時毘盧遮那世尊與一切諸佛同共集會，\n");
    expect(typed(segs).slice(0, 2)).toEqual(["juan:大毘盧遮那成佛神變加持經卷第二", "byline:大唐天竺三藏善無畏共沙門一行譯"]);
  });

  it("卷第 / 五：裸数字的后半截并回卷题", () => {
    const segs = reflowText("菩提場所說一字頂輪王經卷第\n五\n開府儀同三司特進試鴻臚卿\n");
    expect(typed(segs)[0]).toBe("juan:菩提場所說一字頂輪王經卷第五");
  });

  it("三昧大教王經：前半截经名 + 「…經卷第一」合为一个卷题", () => {
    const raw =
      "佛說一切如來真實攝大乘現證\n三昧大教王經卷第一\n西天譯經三藏朝奉大夫試光祿卿\n傳法大師賜紫沙門臣施護等\n奉　詔譯\n金剛界大曼拏羅廣大儀軌分第一之一\n\n如是我聞：\n";
    const segs = reflowText(raw);
    expect(typed(segs).slice(0, 2)).toEqual([
      "juan:佛說一切如來真實攝大乘現證三昧大教王經卷第一",
      "byline:西天譯經三藏朝奉大夫試光祿卿傳法大師賜紫沙門臣施護等奉　詔譯",
    ]);
    expectOffsetsExact(raw, segs);
  });

  it("品题折行：「…教理分第二 / 十六之三」合为一个品题，不进正文", () => {
    const raw = "奉　詔譯\n一切如來真實攝一切儀軌勝上教理分第二\n十六之三\n\n「復次，宣說諸部通用祕密身語心金剛印成就教理。\n";
    const segs = reflowText(raw);
    expect(typed(segs)).toContain("section:一切如來真實攝一切儀軌勝上教理分第二十六之三");
    expect(segs.some((s) => s.type === "prose" && s.text.startsWith("十六之三"))).toBe(false);
    expectOffsetsExact(raw, segs);
  });

  it("卷中品题折行：「…護摩品第 / 三」并成品题，不再粘在上一段正文末尾（吽迦陀野儀軌）", () => {
    const raw = "法相應事。當行者至心聞是大密相應大法，\n聞即信受。」\n吽迦陀野一面十臂摩訶神王𮥟護摩品第\n三\n\n「修真言行者，當至心如法清淨奉持，不生一\n";
    const segs = reflowText(raw);
    expect(typed(segs)).toContain("section:吽迦陀野一面十臂摩訶神王𮥟護摩品第三");
    expect(segs.some((s) => s.type === "prose" && s.text.includes("護摩品"))).toBe(false);
    expectOffsetsExact(raw, segs);
  });

  it("卷中品题折行：「…洗浴品 / 第五」同样成立", () => {
    const segs = reflowText("吽迦陀野儀軌下\n吽迦陀野相應天成就八界供養洗浴品\n第五\n\n「我今依相應天說五種種不思議法。先行者\n");
    expect(typed(segs)).toContain("section:吽迦陀野相應天成就八界供養洗浴品第五");
  });

  it("反例：品字结尾的行后接序数、但其后不是空行（仍在正文中）不并", () => {
    const segs = reflowText("經卷第一\n\n如是我聞：一時佛說此品\n第一義諦\n名為甚深。\n");
    expect(segs.some((s) => s.type === "section")).toBe(false);
  });

  it("反例：引文抽屉从卷中切出的 chunk，首两行是目录里的无标点行（其后不是署名）不并成经题", () => {
    const raw = "法喜堂詩敘山茨堂敘趣軒敘山\n游唱和詩集敘山游詩後序與月上\n人更字敘周感之更字敘送潯陽姚\n駕部敘送郭公甫朝奉詩敘送王仲\n";
    const segs = reflowText(raw);
    expect(segs.some((s) => s.type === "head" && s.text.startsWith("法喜堂"))).toBe(false);
    // 「…經 / 卷上」形状但下一行是正文而非署名，同样不并
    const segs2 = reflowText("文殊師利菩薩及諸仙所說吉凶時日善惡宿\n卷上\n右佛法性身湛然常住。\n");
    expect(segs2.some((s) => s.type !== "break" && s.text.endsWith("宿卷上"))).toBe(false);
  });

  it("反例：经录里的书目行（下一行带「N卷」，不是署名）不并成经题", () => {
    const segs = reflowText("翻經臨壇大德西明安國兩寺上座乘如表狀\n集三卷\n般若三藏續古今翻譯經圖紀二卷\n");
    expect(segs.some((s) => s.type === "head" && s.text.startsWith("翻經"))).toBe(false);
  });

  it("反例：目錄页「旅泊菴稿目錄 / 卷第一」不并（首行太短，不是折行）", () => {
    const segs = reflowText("旅泊菴稿目錄\n卷第一\n法語\n首序\n");
    expect(typed(segs)).not.toContain("juan:旅泊菴稿目錄卷第一");
    expect(typed(segs)).toContain("juan:卷第一");
  });

  it("反例：首行已是完整品题（以序数结尾）时，下一行的「品第一」照旧是独立品题", () => {
    const segs = reflowText("長阿含經卷第一\n序品第一\n\n如是我聞：\n");
    expect(typed(segs).slice(0, 2)).toEqual(["juan:長阿含經卷第一", "section:序品第一"]);
  });

  it("反例：首行是署名时，下一行的「第一」不往署名上并", () => {
    const segs = reflowText("龍樹菩薩造\n第一\n");
    expect(segs.some((s) => s.type === "byline" && s.text.includes("第一"))).toBe(false);
  });

  it("反例：品题后接带标点的正文行，不并", () => {
    const segs = reflowText("觀行品第二\n十六日中，佛在舍衛國。\n");
    expect(typed(segs)).toContain("section:觀行品第二");
    expect(segs.some((s) => s.type === "section" && s.text.includes("十六"))).toBe(false);
  });
});

describe("reflowText — 卷首品题", () => {
  it("四分律卷二十一：署名后的「百眾學法之三」是品题，正文首段从「爾時」起", () => {
    const raw = "四分律卷第二十一\n\n姚秦罽賓三藏佛陀耶舍\n共竺佛念等譯\n百眾學法之三\n\n爾時佛在舍衛國祇樹給孤獨園。時有居士\n請諸比丘欲供設種種飲食，\n";
    const segs = reflowText(raw);
    expect(typed(segs).slice(0, 4)).toEqual([
      "juan:四分律卷第二十一",
      "byline:姚秦罽賓三藏佛陀耶舍共竺佛念等譯",
      "section:百眾學法之三",
      "prose:爾時佛在舍衛國祇樹給孤獨園。時有居士請諸比丘欲供設種種飲食，",
    ]);
    expectOffsetsExact(raw, segs);
  });

  it("四分律卷二十二：无「之N」的「八波羅夷法」也是品题", () => {
    const segs = reflowText("四分律卷第二十二\n姚秦罽賓三藏佛陀耶舍\n共竺佛念等譯\n八波羅夷法\n\n爾時世尊在毘舍離獼猴江邊樓閣講堂\n上。\n");
    expect(typed(segs)[2]).toBe("section:八波羅夷法");
  });

  it("反例：署名后第二位署名人（含全角空格、以「釋」结尾）不当品题", () => {
    const segs = reflowText("四分律藏大小持戒犍度略釋\n三藏佛陀耶舍共竺佛念　譯\n菩薩沙彌古吳智旭際明　釋\n\n此一犍度略釋二義一當分明義\n");
    expect(segs.some((s) => s.type === "section")).toBe(false);
  });

  it("反例：署名后的无标点短行若后面没有空行（还在折行中），不当品题", () => {
    const segs = reflowText("鐔津文集卷第九\n藤州鐔津東山沙門契嵩撰\n再書上\n仁宗皇帝\n\n");
    expect(segs.some((s) => s.type === "section")).toBe(false);
  });

  it("反例：正文已经开始后，空行前的无标点短行不当品题", () => {
    const segs = reflowText("四分律卷第一\n共竺佛念等譯\n\n爾時佛在舍衛國。\n\n彼比丘尼\n\n");
    expect(segs.some((s) => s.type === "section")).toBe(false);
  });

  it("反例：chunk 从署名末行切起（前面没有经题/卷题），其后的无标点短行不当品题", () => {
    const segs = reflowText("塞部撰\n萬治二歲九月吉日\n\n");
    expect(segs.some((s) => s.type === "section")).toBe(false);
  });

  it("反例：经题后的「失譯人名附後漢錄」不是品题（前一行不是署名或卷题）", () => {
    const segs = reflowText("佛說魔嬈亂經\n失譯人名附後漢錄\n\n聞如是：\n");
    expect(segs.some((s) => s.type === "section")).toBe(false);
  });
});
