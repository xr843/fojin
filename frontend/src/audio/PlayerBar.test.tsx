import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import PlayerBar from "./PlayerBar";
import { AudioPlayerContext, type AudioPlayerState } from "./useAudioPlayback";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

function state(overrides: Partial<AudioPlayerState> = {}): AudioPlayerState {
  return {
    track: {
      textId: 9,
      juanNum: 1,
      title: "般若波羅蜜多心經 第1卷",
      audio: {
        text_id: 9,
        juan_num: 1,
        url: "/audio/9/1-a328034b.mp3",
        voice_id: "Chinese (Mandarin)_Lyrical_Voice",
        engine: "minimax",
        duration_ms: 108_035,
        cues: [],
      },
    },
    playing: false,
    cueIndex: -1,
    rate: 1,
    positionMs: 0,
    play: vi.fn(),
    toggle: vi.fn(),
    seek: vi.fn(),
    setRate: vi.fn(),
    stop: vi.fn(),
    ...overrides,
  };
}

const renderWith = (s: AudioPlayerState) =>
  render(
    <AudioPlayerContext.Provider value={s}>
      <PlayerBar />
    </AudioPlayerContext.Provider>,
  );

describe("PlayerBar", () => {
  it("必须显示「AI 合成朗读」标注", () => {
    // 诚信约束：不得让用户以为是法师读诵。这不是样式偏好，是产品底线。
    renderWith(state());
    expect(screen.getByText("reader.audio.synthetic_label")).toBeTruthy();
  });

  it("必须渲染合成声明", () => {
    // 声明必须真实出现在 DOM 里，不能只躺在 JSON 里
    renderWith(state());
    expect(screen.getByLabelText("reader.audio.model_disclaimer")).toBeTruthy();
  });

  it("显示当前曲目标题", () => {
    renderWith(state());
    expect(screen.getByText(/般若波羅蜜多心經 第1卷/)).toBeTruthy();
  });

  it("显示已播时间与总时长", () => {
    renderWith(state({ positionMs: 65_000 }));
    expect(screen.getByText("1:05")).toBeTruthy();
    expect(screen.getByText("1:48")).toBeTruthy(); // 108035ms
  });

  it("无 track 时不渲染任何内容", () => {
    const { container } = renderWith(state({ track: null }));
    expect(container.textContent).toBe("");
  });
});
