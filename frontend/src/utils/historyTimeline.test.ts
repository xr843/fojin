import { describe, expect, it } from "vitest";
import { aliveAt, fixZhuAfterSimplify, formatYears, layoutLanes, packRows, personSpan, translationRiver, type HistoryPerson } from "./historyTimeline";
import { dynastyAt, dynastySpan } from "../data/historyDynasties";

function person(over: Partial<HistoryPerson>): HistoryPerson {
  return { id: "A1", n: "某", dn: "某", alt: [], dy: "唐", sc: "禅", b: null, d: null, monk: true, tr: false, bio: "", te: [], st: [], bios: [], men: [], works: [], wn: 0, ...over };
}

describe("佛教史长卷排布", () => {
  it("生卒俱全：按生卒画条；DILA 记成区间的年份标「约」", () => {
    const xz = person({ n: "玄奘", b: [602, 603], d: [664, 664] });
    expect(personSpan(xz)).toEqual({ start: 602, end: 664, kind: "full", approx: true });
    expect(formatYears(xz, "约")).toBe("约602–664");
    expect(formatYears(person({ b: [638, 638], d: [713, 713] }))).toBe("638–713");
  });

  it("只知卒年：往前推 60 年起头，算推算", () => {
    expect(personSpan(person({ d: [535, 536] }))).toEqual({ start: 475, end: 536, kind: "death", approx: true });
  });

  it("生卒不详：用小传里落在本朝的纪年定位（安世高「建和二年（148）」）", () => {
    const an = person({ dy: "東漢", bio: "桓帝建和二年（148），經西域諸國至洛陽譯經，凡二十餘年" });
    expect(personSpan(an)).toEqual({ start: 138, end: 158, kind: "bio", approx: true });
  });

  it("生卒不详、小传也无纪年：落在朝代上，且不算「某年在世」", () => {
    const p = person({ dy: "北魏 東魏" });
    const s = personSpan(p);
    expect(s).toEqual({ start: 386, end: 534, kind: "dynasty", approx: true });
    expect(aliveAt(s, 500)).toBe(false);
  });

  it("小传里的纪年不在本朝范围内的不采用", () => {
    expect(personSpan(person({ dy: "東漢", bio: "後人於明萬曆（1600）重刻其經" }))?.kind).toBe("dynasty");
  });

  it("分行：时间重叠的人不在同一行，名字占的地方也算", () => {
    const a = person({ id: "a", b: [600, 600], d: [650, 650] });
    const b = person({ id: "b", b: [640, 640], d: [700, 700] });
    const c = person({ id: "c", b: [655, 655], d: [700, 700] });
    const noLabel = packRows([a, b, c], 1, () => 0, 0);
    expect(noLabel.rows).toBe(2);
    expect(noLabel.placed.find((x) => x.person.id === "c")?.row).toBe(0);
    // 名字有 40px 宽：a 的名字写到 690，c（655 起）只能换行
    const withLabel = packRows([a, b, c], 1, () => 40, 0);
    expect(withLabel.rows).toBe(3);
  });

  it("分行：只知朝代的人排在所有有年份的人下面", () => {
    const a = person({ id: "a", b: [600, 600], d: [650, 650] });
    const u = person({ id: "u", dy: "唐" });
    const { placed, rows } = packRows([u, a], 1, () => 0, 0);
    expect(rows).toBe(2);
    expect(placed.find((x) => x.person.id === "u")?.row).toBe(1);
  });

  it("宗派泳道：按既定先后排，每条泳道先占一行标题；不认识的宗派归「其他」", () => {
    const chan = person({ id: "c", sc: "禅", b: [638, 638], d: [713, 713] });
    const tr = person({ id: "t", sc: "译经", b: [602, 602], d: [664, 664] });
    const tr2 = person({ id: "t2", sc: "译经", b: [610, 610], d: [660, 660] });
    const odd = person({ id: "x", sc: "某宗", b: [700, 700], d: [760, 760] });
    const { items, lanes, rows } = layoutLanes([chan, tr, tr2, odd], 1, () => 0, (p) => p.sc);
    expect(lanes.map((l) => [l.key, l.firstRow, l.rows, l.count])).toEqual([
      ["译经", 0, 3, 2],
      ["禅", 3, 2, 1],
      ["其他", 5, 2, 1],
    ]);
    expect(rows).toBe(7);
    expect(items.find((i) => i.person.id === "c")?.row).toBe(4);
    expect(items.find((i) => i.person.id === "x")?.row).toBe(6);
  });

  it("按年代看：不分泳道", () => {
    const { lanes, rows } = layoutLanes([person({ b: [600, 600], d: [650, 650] })], 1, () => 0, null);
    expect(lanes).toEqual([]);
    expect(rows).toBe(1);
  });

  it("译经长河：只算译经师，著译部数摊进生卒条的后三分之二", () => {
    const tr = person({ tr: true, wn: 30, b: [600, 600], d: [690, 690] });
    const bins = translationRiver([tr, person({ wn: 99, b: [600, 600], d: [690, 690] })], 600, 700, 10);
    const total = bins.reduce((s, x) => s + x, 0);
    expect(total).toBeCloseTo(30, 5);
    expect(bins[0]).toBe(0); // 600–609 在前三分之一，不摊
  });

  it("朝代：DILA 的「東晉 後秦」取第一个认得的；某年落在哪朝", () => {
    expect(dynastySpan("東晉 後秦")).toEqual([317, 420]);
    expect(dynastySpan("後秦")).toEqual([384, 417]);
    expect(dynastyAt(645)?.name).toBe("唐");
    expect(dynastyAt(270)?.name).toBe("西晉");
  });

  it("繁转简后把表示著述的「着」改回「著」，助词「着」不动", () => {
    expect(fixZhuAfterSimplify("着《佛国记》")).toBe("著《佛国记》");
    expect(fixZhuAfterSimplify("着有《宗镜录》、另着〈唯心诀〉")).toBe("著有《宗镜录》、另著〈唯心诀〉");
    expect(fixZhuAfterSimplify("撰着、所着")).toBe("撰著、所著");
    expect(fixZhuAfterSimplify("随着时代，接着又往南岳")).toBe("随着时代，接着又往南岳");
    expect(fixZhuAfterSimplify("文偃为最着，杂着被编为三十卷")).toBe("文偃为最著，杂著被编为三十卷");
    expect(fixZhuAfterSimplify("讲无量寿经，着安乐集二卷")).toBe("讲无量寿经，著安乐集二卷");
    expect(fixZhuAfterSimplify("随着论疏，接着讲记")).toBe("随着论疏，接着讲记");
  });
});
