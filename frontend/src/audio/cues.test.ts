import { describe, it, expect } from "vitest";
import { findCueIndex } from "./cues";
import type { AudioCue } from "../api/client";

const cue = (time_ms: number, char_start: number, char_end: number): AudioCue => ({
  time_ms,
  char_start,
  char_end,
  kind: "prose",
});

// 三段：0-2.5s / 2.5-5s / 5s-末尾
const CUES: AudioCue[] = [cue(0, 0, 10), cue(2500, 10, 20), cue(5000, 20, 30)];

describe("findCueIndex", () => {
  it("空数组返回 -1", () => {
    expect(findCueIndex([], 1000)).toBe(-1);
  });

  it("时间落在第一段区间内", () => {
    expect(findCueIndex(CUES, 0)).toBe(0);
    expect(findCueIndex(CUES, 1200)).toBe(0);
  });

  it("边界值归属后一段，不是前一段", () => {
    // 2500 正好是第二段起点 —— 归 1，否则高亮会慢半拍
    expect(findCueIndex(CUES, 2500)).toBe(1);
    expect(findCueIndex(CUES, 5000)).toBe(2);
  });

  it("超出末段时间仍停在末段", () => {
    expect(findCueIndex(CUES, 999999)).toBe(2);
  });

  it("负时间返回 -1", () => {
    expect(findCueIndex(CUES, -1)).toBe(-1);
  });

  it("大数组上结果与线性扫描一致", () => {
    // 二分最容易在中间某处偏一位，用线性扫描做交叉验证
    const many: AudioCue[] = Array.from({ length: 500 }, (_, i) =>
      cue(i * 1000, i * 10, i * 10 + 10),
    );
    const linear = (t: number) => {
      let hit = -1;
      for (let i = 0; i < many.length; i += 1) if (many[i].time_ms <= t) hit = i;
      return hit;
    };
    for (const t of [0, 1, 999, 1000, 250_500, 499_000, 499_999, 1_000_000]) {
      expect(findCueIndex(many, t)).toBe(linear(t));
    }
  });

  it("真实心經 cue 时间轴（13 段）", () => {
    // 取自 build_audio.py 的实际产物：经名 0ms / 译者 1996ms / 正文 5235ms
    const real: AudioCue[] = [
      { time_ms: 0, char_start: 0, char_end: 8, kind: "head" },
      { time_ms: 1996, char_start: 9, char_end: 17, kind: "byline" },
      { time_ms: 5235, char_start: 19, char_end: 48, kind: "prose" },
    ];
    expect(findCueIndex(real, 0)).toBe(0);
    expect(findCueIndex(real, 1995)).toBe(0);
    expect(findCueIndex(real, 1996)).toBe(1);
    expect(findCueIndex(real, 5234)).toBe(1);
    expect(findCueIndex(real, 5235)).toBe(2);
  });
});
