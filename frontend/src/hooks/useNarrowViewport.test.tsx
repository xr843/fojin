import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { NARROW_VIEWPORT_QUERY, isNarrowViewport, useNarrowViewport } from "./useNarrowViewport";

type ChangeListener = (e: { matches: boolean }) => void;

/** 装一个可手动触发 change 的 matchMedia；只对 NARROW_VIEWPORT_QUERY 回答 matches。 */
function installMatchMedia(matches: boolean) {
  const listeners = new Set<ChangeListener>();
  const mql = {
    matches,
    media: NARROW_VIEWPORT_QUERY,
    onchange: null,
    addEventListener: (_: string, cb: ChangeListener) => { listeners.add(cb); },
    removeEventListener: (_: string, cb: ChangeListener) => { listeners.delete(cb); },
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  };
  window.matchMedia = vi.fn((q: string) =>
    q === NARROW_VIEWPORT_QUERY ? mql : { ...mql, matches: false, media: q },
  ) as unknown as typeof window.matchMedia;
  return {
    fire(next: boolean) {
      mql.matches = next;
      listeners.forEach((cb) => cb({ matches: next }));
    },
    listenerCount: () => listeners.size,
  };
}

const originalMatchMedia = window.matchMedia;
afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

describe("useNarrowViewport", () => {
  it("matchMedia 缺失（jsdom / SSR）时按宽屏处理，不抛错", () => {
    // @ts-expect-error 故意拆掉，模拟没有 matchMedia 的环境
    delete window.matchMedia;
    expect(isNarrowViewport()).toBe(false);
    const { result } = renderHook(() => useNarrowViewport());
    expect(result.current).toBe(false);
  });

  it("窄屏首帧即为 true，断点变化时跟随，卸载后不再监听", () => {
    const mm = installMatchMedia(true);
    expect(isNarrowViewport()).toBe(true);
    const { result, unmount } = renderHook(() => useNarrowViewport());
    expect(result.current).toBe(true);

    act(() => mm.fire(false));
    expect(result.current).toBe(false);

    act(() => mm.fire(true));
    expect(result.current).toBe(true);

    unmount();
    expect(mm.listenerCount()).toBe(0);
  });
});
