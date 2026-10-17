import { describe, expect, it } from "vitest";
import {
  formatCbetaCitation,
  formatLineRange,
  lineHead,
  lineLevelSupported,
  parseCbetaLocator,
  parseStem,
  stemFor,
  type CbetaStems,
} from "./cbetaCitation";

const STEMS: CbetaStems = {
  T0235: "T08n0235",
  T0128a: "T02n0128a",
  X0240: [[1, "X08n0240"], [45, "X09n0240"]],
};

describe("stemFor", () => {
  it("单册经直接给文件主名", () => {
    expect(stemFor(STEMS, "T0235", 1)).toBe("T08n0235");
  });
  it("跨册的经按卷取册：第 44 卷在 X08，第 45 卷起在 X09", () => {
    expect(stemFor(STEMS, "X0240", 44)).toBe("X08n0240");
    expect(stemFor(STEMS, "X0240", 45)).toBe("X09n0240");
    expect(stemFor(STEMS, "X0240", 80)).toBe("X09n0240");
  });
  it("查不到返回 null", () => {
    expect(stemFor(STEMS, "T9999", 1)).toBeNull();
    expect(stemFor(null, "T0235", 1)).toBeNull();
  });
});

describe("parseStem", () => {
  it("去掉经号前导零，保留字母后缀", () => {
    expect(parseStem("T08n0235")).toEqual({ collection: "T", volume: "T08", no: "235" });
    expect(parseStem("T02n0128a")).toEqual({ collection: "T", volume: "T02", no: "128a" });
    expect(parseStem("J01nA042")).toEqual({ collection: "J", volume: "J01", no: "A42" });
  });
});

describe("formatLineRange（照 CBETA 引用複製实测写法）", () => {
  it("单行", () => expect(formatLineRange("0749a05")).toBe("p. 749a5"));
  it("同栏跨行", () => expect(formatLineRange("0749a05", "0749a07")).toBe("p. 749a5-7"));
  it("跨栏", () => expect(formatLineRange("0749a28", "0749b02")).toBe("p. 749a28-b2"));
  it("跨页", () => expect(formatLineRange("0749a28", "0750b03")).toBe("pp. 749a28-750b3"));
  it("起止同一行不写范围", () => expect(formatLineRange("0749a05", "0749a05")).toBe("p. 749a5"));
  it("非行号格式返回 null", () => expect(formatLineRange("749a5")).toBeNull());
});

describe("formatCbetaCitation", () => {
  it("单卷经省略卷号，给到页栏行（不写我们核对不了的版本号）", () => {
    expect(
      formatCbetaCitation({
        title: "金剛般若波羅蜜經",
        juan: 1,
        juanCount: 1,
        quote: "佛告須菩提：\n諸菩薩摩訶薩 應如是降伏其心",
        cbetaId: "T0235",
        stem: "T08n0235",
        startRef: "0749a05",
        endRef: "0749a07",
      }),
    ).toBe("《金剛般若波羅蜜經》：「佛告須菩提：諸菩薩摩訶薩應如是降伏其心」(CBETA, T08, no. 235, p. 749a5-7)");
  });

  it("多卷经带卷号；选区内的校勘注接在出处后面", () => {
    expect(
      formatCbetaCitation({
        title: "阿毘達磨俱舍論",
        juan: 3,
        juanCount: 30,
        quote: "[1]根",
        cbetaId: "T1558",
        stem: "T29n1558",
        startRef: "0013b11",
        notes: ["[1] 根【大】，境【宋】"],
      }),
    ).toBe("《阿毘達磨俱舍論》卷3：「[1]根」(CBETA, T29, no. 1558, p. 13b11)[1] 根【大】，境【宋】");
  });

  it("卍续藏只给到册与经号：库里的 X 行号混着 R 版页码，给页栏行会出错", () => {
    expect(
      formatCbetaCitation({
        title: "金剛經註疏",
        juan: 1,
        juanCount: 3,
        quote: "如是",
        cbetaId: "X0456",
        stem: "X24n0456",
        startRef: "0706a04",
      }),
    ).toBe("《金剛經註疏》卷1：「如是」(CBETA, X24, no. 456)");
  });

  it("没有册号数据时退回经号", () => {
    expect(
      formatCbetaCitation({ title: "某經", juan: 2, juanCount: 4, quote: "文", cbetaId: "T9999", stem: null, startRef: "0001a01" }),
    ).toBe("《某經》卷2：「文」(CBETA, T9999)");
  });
});

describe("lineHead / lineLevelSupported", () => {
  it("行首格式", () => expect(lineHead("T08n0235", "0749a05")).toBe("T08n0235_p0749a05"));
  it("只有大正藏开放行级", () => {
    expect(lineLevelSupported("T0235")).toBe(true);
    expect(lineLevelSupported("X0456")).toBe(false);
  });
});

describe("parseCbetaLocator", () => {
  it("行首", () => {
    expect(parseCbetaLocator("T08n0235_p0749a05")).toEqual({ cbetaId: "T0235", ref: "0749a05" });
    expect(parseCbetaLocator(" T02n0128a_p0835b12 ")).toEqual({ cbetaId: "T0128a", ref: "0835b12" });
  });
  it("书目格式，含版本号与页码范围（取起点）", () => {
    expect(parseCbetaLocator("(CBETA 2026.R2, T08, no. 235, p. 749a5-7)")).toEqual({ cbetaId: "T0235", ref: "0749a05" });
    expect(parseCbetaLocator("T29, no. 1558, pp. 13b11-14a2")).toEqual({ cbetaId: "T1558", ref: "0013b11" });
  });
  it("整段引用文字粘进来也认得出处", () => {
    expect(
      parseCbetaLocator("《金剛般若波羅蜜經》卷1：「佛告須菩提」(CBETA 2026.R2, T08, no. 235, p. 749a5-7)"),
    ).toEqual({ cbetaId: "T0235", ref: "0749a05" });
  });
  it("普通检索词不误认", () => {
    expect(parseCbetaLocator("T0235")).toBeNull();
    expect(parseCbetaLocator("金剛經 p. 5")).toBeNull();
  });
});
