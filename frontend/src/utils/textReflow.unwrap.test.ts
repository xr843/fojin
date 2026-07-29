import { describe, it, expect } from "vitest";
import { unwrapCbetaLines } from "./textReflow";

/**
 * CBETA 正文每 ~18 字一个硬换行（版式，非语义）。任何把 chunk_text 直接塞进
 * DOM 的地方，HTML 都会把这些 \n 折叠成空格，于是「三清淨」显示成「三清 淨」。
 * 2026-07-29 用户在引文抽屉里发现，核查后确认相似段落与跨藏对读面板同样中招。
 */
describe("unwrapCbetaLines", () => {
  it("段内硬换行处不得留下任何分隔符——中文没有词间空格", () => {
    expect(unwrapCbetaLines("又經中言有三清\n淨，俱身語意。")).toBe(
      "又經中言有三清淨，俱身語意。",
    );
    expect(unwrapCbetaLines("意牟尼即無\n學意非意業。")).toBe("意牟尼即無學意非意業。");
  });

  it("空行是真正的段落边界，必须保留", () => {
    expect(unwrapCbetaLines("業來責報準\n此可解。\n\n復次，諸業名、教、體、相。")).toBe(
      "業來責報準此可解。\n\n復次，諸業名、教、體、相。",
    );
  });

  it("不得丢字", () => {
    const raw = "有愛，乃至廣說如是見\n者違害於我，我今不應與怨同見。彼由\n憎恚，起如是見";
    expect(unwrapCbetaLines(raw).replace(/\n/g, "")).toBe(raw.replace(/\n/g, ""));
  });

  it("行首行尾的空白一并清掉，避免转成可见空格", () => {
    expect(unwrapCbetaLines("此可解。 \n  復次")).toBe("此可解。復次");
  });

  it("无换行的文本原样返回", () => {
    expect(unwrapCbetaLines("已經是一整句了。")).toBe("已經是一整句了。");
  });
});
