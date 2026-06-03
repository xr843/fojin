import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSelectedChunks } from "./useSelectedChunks";

describe("useSelectedChunks", () => {
  it("starts empty", () => {
    const { result } = renderHook(() => useSelectedChunks());
    expect(result.current.selected).toEqual([]);
  });

  it("toggles a chunk on / off", () => {
    const { result } = renderHook(() => useSelectedChunks());
    const c = { text_id: 100, juan_num: 1, chunk_index: 0, lang: "lzh", text: "觀" };
    act(() => result.current.toggle(c));
    expect(result.current.selected).toHaveLength(1);
    act(() => result.current.toggle(c));
    expect(result.current.selected).toHaveLength(0);
  });

  it("dedupes by (text_id, chunk_index)", () => {
    const { result } = renderHook(() => useSelectedChunks());
    const c1 = { text_id: 100, juan_num: 1, chunk_index: 0, lang: "lzh", text: "觀" };
    const c1Dup = { ...c1, text: "觀X" };
    act(() => result.current.toggle(c1));
    act(() => result.current.toggle(c1Dup));
    expect(result.current.selected).toHaveLength(0);
  });

  it("clear() empties selection", () => {
    const { result } = renderHook(() => useSelectedChunks());
    const a = { text_id: 100, juan_num: 1, chunk_index: 0, lang: "lzh", text: "觀" };
    const b = { text_id: 200, juan_num: 1, chunk_index: 0, lang: "en", text: "Av" };
    act(() => result.current.toggle(a));
    act(() => result.current.toggle(b));
    expect(result.current.selected).toHaveLength(2);
    act(() => result.current.clear());
    expect(result.current.selected).toHaveLength(0);
  });
});
