import { describe, it, expect } from "vitest";
import { satLineUrl, satTextUrl, taishoVolume } from "./satUrls";
import cbeta from "./__fixtures__/taishoVolumes.cbeta.json";

const FILES = cbeta as Record<string, number[]>;

describe("taishoVolume 大正藏册号", () => {
  it("对 CBETA xml-p5 全部大正藏文件逐一往返一致（区间表没有错位）", () => {
    let checked = 0;
    for (const [no, vols] of Object.entries(FILES)) {
      if (no === "0220") continue;
      expect(vols).toHaveLength(1);
      expect(taishoVolume(`T${no}`), `T${no}`).toBe(vols[0]);
      checked++;
    }
    expect(checked).toBeGreaterThan(2300);
  });

  it("T0220 大般若经按 fojin 的 a/b/c 分部或卷号落到第 5/6/7 册", () => {
    expect(taishoVolume("T0220a")).toBe(5);
    expect(taishoVolume("T0220b")).toBe(6);
    expect(taishoVolume("T0220c")).toBe(7);
    expect(taishoVolume("T0220", 150)).toBe(5);
    expect(taishoVolume("T0220", 401)).toBe(7);
    expect(taishoVolume("T0220")).toBeNull();
  });

  it("CBETA 未收的第 56–84 册号段、非大正藏经号一律 null，不猜", () => {
    expect(taishoVolume("T2185")).toBeNull();
    expect(taishoVolume("T2731")).toBeNull();
    expect(taishoVolume("T2921")).toBeNull();
    expect(taishoVolume("X0506")).toBeNull();
    expect(taishoVolume("T0235x1")).toBeNull();
  });
});

describe("SAT 链接", () => {
  it("行级链接带册号（浏览器实测可定位到该行）", () => {
    expect(satLineUrl("T0235", "0748c24")).toBe("https://21dzk.l.u-tokyo.ac.jp/SAT2018/T0235_.08.0748c24.html");
    expect(satLineUrl("T0220b", "0001a01")).toBe("https://21dzk.l.u-tokyo.ac.jp/SAT2018/T0220_.06.0001a01.html");
  });

  it("经页面不用会落到 SAT 首页的 master30.php", () => {
    expect(satTextUrl("T0235")).toBe("https://21dzk.l.u-tokyo.ac.jp/SAT2018/T0235.html");
    expect(satTextUrl("T0235")).not.toContain("master30");
  });

  it("拿不到册号或行号畸形时退回经页面；非大正藏不给链接", () => {
    expect(satLineUrl("T0220", "0001a01")).toBe("https://21dzk.l.u-tokyo.ac.jp/SAT2018/T0220.html");
    expect(satLineUrl("T0235", "garbage")).toBe("https://21dzk.l.u-tokyo.ac.jp/SAT2018/T0235.html");
    expect(satLineUrl("X0506", "0001a01")).toBeNull();
  });
});
