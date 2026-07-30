import { describe, expect, it } from "vitest";
import { isNearBottom, NEAR_BOTTOM_PX } from "./scrollBottom";

/** 造一个只有滚动几何的假元素 —— isNearBottom 只读这三个数。 */
function box(scrollHeight: number, scrollTop: number, clientHeight: number) {
  return { scrollHeight, scrollTop, clientHeight };
}

describe("isNearBottom", () => {
  it("滚到底为真", () => {
    expect(isNearBottom(box(1000, 600, 400))).toBe(true);
  });

  it("停在顶部为假", () => {
    expect(isNearBottom(box(1000, 0, 400))).toBe(false);
  });

  it("阈值边界：差 79px 为真，80px 为假", () => {
    // distance = scrollHeight - scrollTop - clientHeight
    expect(isNearBottom(box(1000, 521, 400))).toBe(true); // 79
    expect(isNearBottom(box(1000, 520, 400))).toBe(false); // 80
  });

  it("内容不足以滚动时为真（空状态不该显示回到底部按钮）", () => {
    expect(isNearBottom(box(400, 0, 400))).toBe(true);
  });

  it("元素还不存在时为真（首个 token 仍要滚进视野）", () => {
    expect(isNearBottom(null)).toBe(true);
  });

  it("阈值是 80", () => {
    expect(NEAR_BOTTOM_PX).toBe(80);
  });
});
