import { describe, it, expect, vi, afterEach } from "vitest";

import { trackAudio } from "./telemetry";

function withUmami(fn: (track: ReturnType<typeof vi.fn>) => void) {
  const track = vi.fn();
  vi.stubGlobal("umami", { track });
  fn(track);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("trackAudio", () => {
  it("带上 text_id 与 juan_num —— 否则只知道「有人听」，不知道听的是哪部经", () => {
    withUmami((track) => {
      trackAudio("audio_play", 9, 1);
      expect(track).toHaveBeenCalledWith("audio_play", { text_id: 9, juan_num: 1 });
    });
  });

  it("umami 未加载时静默跳过，不抛异常", () => {
    // 自托管者不配 VITE_UMAMI_* 就不会注入脚本（见 src/umami.ts），
    // 埋点不能因此让播放器崩掉。
    vi.stubGlobal("umami", undefined);
    expect(() => trackAudio("audio_play", 9, 1)).not.toThrow();
  });

  it("事件名原样透传", () => {
    withUmami((track) => {
      trackAudio("audio_complete", 7, 2);
      expect(track).toHaveBeenCalledWith("audio_complete", { text_id: 7, juan_num: 2 });
    });
  });
});
