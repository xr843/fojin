import { describe, it, expect, vi, afterEach } from "vitest";
import { captureScrollAnchor, restoreScrollAnchor } from "./scrollAnchor";

function fakeRange(top: number, inside: Node): Range {
  return {
    commonAncestorContainer: inside,
    getClientRects: () => [{ top }] as unknown as DOMRectList,
    getBoundingClientRect: () => ({ top, width: 10, height: 10 }) as DOMRect,
    cloneRange() { return this as unknown as Range; },
  } as unknown as Range;
}

afterEach(() => vi.restoreAllMocks());

describe("scrollAnchor", () => {
  it("优先用视口内的选区做锚点", () => {
    const box = document.createElement("div");
    const txt = document.createTextNode("有十四音名為字義");
    box.appendChild(txt);
    document.body.appendChild(box);
    const a = captureScrollAnchor(box, fakeRange(367, txt));
    expect(a?.top).toBe(367);
    box.remove();
  });

  it("版面变化后把锚点滚回原来的屏幕位置（整页滚动）", () => {
    const box = document.createElement("div");
    document.body.appendChild(box);
    const spy = vi.spyOn(window, "scrollBy").mockImplementation(() => {});
    // 记下时在 367，面板打开重排后跑到 5962 —— 需要往下滚 5595
    restoreScrollAnchor({ range: fakeRange(5962, box), top: 367 }, box);
    expect(spy).toHaveBeenCalledWith(0, 5595);
    box.remove();
  });

  it("位置没变就不滚", () => {
    const box = document.createElement("div");
    const spy = vi.spyOn(window, "scrollBy").mockImplementation(() => {});
    restoreScrollAnchor({ range: fakeRange(300, box), top: 300 }, box);
    expect(spy).not.toHaveBeenCalled();
  });
});
