import { describe, it, expect } from "vitest";
import { coverPoint, BG_NATURAL, PEAK_FRACTION, BG_OBJECT_POS } from "./xiaojinPeak";

/**
 * cover 数学的两种裁切方向各验一例，期望值全部手算：
 * 图 1280×717，山尖比例 (0.8172, 0.4003)，object-position center 70%。
 */
describe("coverPoint（cover 裁切下的比例点→容器坐标）", () => {
  it("宽容器（按宽放大、裁上下）：1920×809 → 山尖 (1578.2, 244.0)", () => {
    // s = max(1920/1280, 809/717) = 1.5 → 渲染 1920×1075.5
    // ox = (1920-1920)*0.5 = 0; oy = (809-1075.5)*0.7 = -186.55
    // x = 0 + 0.822*1920 = 1578.24; y = -186.55 + 0.4003*1075.5 = 243.97
    const pt = coverPoint(1920, 809, BG_NATURAL, PEAK_FRACTION, BG_OBJECT_POS);
    expect(pt.x).toBeCloseTo(1578.24, 1);
    expect(pt.y).toBeCloseTo(243.97, 1);
  });

  it("窄容器（按高放大、裁左右）：390×640 → 山尖溢出右缘（x > 390）", () => {
    // s = max(390/1280, 640/717) = 0.8926 → 渲染 1142.5×640
    // ox = (390-1142.5)*0.5 = -376.3; x = -376.3 + 0.822*1142.5 = 562.9 —— 出画
    const pt = coverPoint(390, 640, BG_NATURAL, PEAK_FRACTION, BG_OBJECT_POS);
    expect(pt.x).toBeGreaterThan(390); // 窄屏山尖被裁掉 → 组件应回退右下角锚点
    expect(pt.x).toBeCloseTo(562.9, 0);
    expect(pt.y).toBeCloseTo(256.2, 0);
  });

  it("object-position 的偏移方向：y=0.7 意味着上边裁得多（山尖上移）", () => {
    const at70 = coverPoint(1920, 809, BG_NATURAL, PEAK_FRACTION, { x: 0.5, y: 0.7 });
    const at50 = coverPoint(1920, 809, BG_NATURAL, PEAK_FRACTION, { x: 0.5, y: 0.5 });
    expect(at70.y).toBeLessThan(at50.y);
  });
});
