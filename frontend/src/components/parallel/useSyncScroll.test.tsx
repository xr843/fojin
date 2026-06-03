import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSyncScroll } from "./useSyncScroll";
import type { AlignmentMap } from "./types";

// jsdom doesn't implement scrollTo on elements
function makeColumnEl(textId: number, chunks: number[]): HTMLDivElement {
  const el = document.createElement("div");
  el.dataset.textId = String(textId);
  Object.defineProperty(el, "scrollHeight", { value: 1000, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: 200, configurable: true });
  el.scrollTop = 0;
  // Add chunk nodes
  for (const idx of chunks) {
    const span = document.createElement("span");
    span.dataset.chunkIndex = String(idx);
    Object.defineProperty(span, "offsetTop", { value: idx * 100, configurable: true });
    Object.defineProperty(span, "offsetHeight", { value: 80, configurable: true });
    el.appendChild(span);
  }
  // Stub scrollTo
  el.scrollTo = vi.fn((opts: ScrollToOptions) => {
    el.scrollTop = (opts as { top: number }).top;
  }) as unknown as Element["scrollTo"];
  return el;
}

describe("useSyncScroll", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("syncs follower to driver via anchor when alignment exists", () => {
    const colA = makeColumnEl(100, [0, 1, 2]);
    const colB = makeColumnEl(200, [5, 6, 7]);
    const map: AlignmentMap = { 100: { 1: { 200: 6 } }, 200: { 6: { 100: 1 } } };
    const refs = { current: [{ textId: 100, el: colA }, { textId: 200, el: colB }] };

    renderHook(() => useSyncScroll(refs, map));

    // Simulate scrolling A so that chunk_index=1 is at top
    colA.scrollTop = 100;
    act(() => {
      colA.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20); // debounce
    });

    expect(colB.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 600 }));
    // chunk 6 in B has offsetTop = 6*100 = 600
  });

  it("falls back to proportional when no anchor for visible chunk", () => {
    const colA = makeColumnEl(100, [0]);
    const colB = makeColumnEl(200, [0]);
    // Map has no entry for A.chunk 0 → B
    const map: AlignmentMap = {};
    const refs = { current: [{ textId: 100, el: colA }, { textId: 200, el: colB }] };

    renderHook(() => useSyncScroll(refs, map));

    // Scroll A to 50% (scrollTop=400 since scrollHeight=1000, clientHeight=200, max=800)
    colA.scrollTop = 400;
    act(() => {
      colA.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20);
    });

    expect(colB.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 400 }));
  });

  it("suppresses programmatic scroll feedback loop (80ms guard)", () => {
    const colA = makeColumnEl(100, [0, 1]);
    const colB = makeColumnEl(200, [5, 6]);
    const map: AlignmentMap = { 100: { 1: { 200: 6 } }, 200: { 6: { 100: 1 } } };
    const refs = { current: [{ textId: 100, el: colA }, { textId: 200, el: colB }] };

    renderHook(() => useSyncScroll(refs, map));

    // First: user scrolls A, B receives programmatic scroll
    colA.scrollTop = 100;
    act(() => {
      colA.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20);
    });
    (colB.scrollTo as ReturnType<typeof vi.fn>).mockClear();
    (colA.scrollTo as ReturnType<typeof vi.fn>).mockClear();

    // Now: B receives its own scroll event (echo) within 80ms — should NOT trigger sync
    colB.scrollTop = 600;
    act(() => {
      colB.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20);
    });

    expect(colA.scrollTo).not.toHaveBeenCalled();
  });

  it("syncs 3 columns when driver scrolls", () => {
    const colA = makeColumnEl(100, [0, 1]);
    const colB = makeColumnEl(200, [5, 6]);
    const colC = makeColumnEl(300, [10, 11]);
    const map: AlignmentMap = {
      100: { 1: { 200: 6, 300: 11 } },
    };
    const refs = {
      current: [
        { textId: 100, el: colA },
        { textId: 200, el: colB },
        { textId: 300, el: colC },
      ],
    };

    renderHook(() => useSyncScroll(refs, map));

    colA.scrollTop = 100;
    act(() => {
      colA.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20);
    });

    expect(colB.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 600 }));
    expect(colC.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 1100 }));
  });
});
