import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AudioPlayerProvider from "./AudioPlayerProvider";
import { useAudioPlayer, type AudioTrack } from "./useAudioPlayback";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const TRACK: AudioTrack = {
  textId: 9,
  juanNum: 1,
  title: "般若波羅蜜多心經 第1卷",
  audio: {
    text_id: 9,
    juan_num: 1,
    url: "/audio/9/1-ba9307ad.mp3",
    voice_id: "Chinese (Mandarin)_Lyrical_Voice",
    engine: "minimax",
    duration_ms: 101_412,
    cues: [],
  },
};

/** Provider 内部用 `new Audio()`，元素不在 DOM 里，只能从构造处截获。 */
let created: HTMLAudioElement[] = [];
let track: ReturnType<typeof vi.fn>;

function Harness() {
  const p = useAudioPlayer();
  return (
    <>
      <button onClick={() => p.play(TRACK)}>go</button>
      <button onClick={() => p.seek(30_000)}>jump</button>
    </>
  );
}

beforeEach(() => {
  created = [];
  track = vi.fn();
  vi.stubGlobal("umami", { track });
  const Orig = window.Audio;
  vi.stubGlobal(
    "Audio",
    class extends Orig {
      constructor(src?: string) {
        super(src);
        created.push(this as unknown as HTMLAudioElement);
      }
    },
  );
  // jsdom 不实现 HTMLMediaElement.play()，不打桩会抛 "Not implemented"
  vi.spyOn(window.HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function start() {
  render(
    <AudioPlayerProvider>
      <Harness />
    </AudioPlayerProvider>,
  );
  await userEvent.click(screen.getByText("go"));
  return created[0];
}

describe("AudioPlayerProvider 埋点", () => {
  it("开播记 audio_play", async () => {
    const el = await start();
    act(() => void el.dispatchEvent(new Event("play")));
    expect(track).toHaveBeenCalledWith("audio_play", { text_id: 9, juan_num: 1 });
  });

  it("同一卷内暂停再播不重复记 audio_play —— 否则「有多少人开始听」会被续播灌水", async () => {
    const el = await start();
    act(() => void el.dispatchEvent(new Event("play")));
    act(() => void el.dispatchEvent(new Event("pause")));
    act(() => void el.dispatchEvent(new Event("play")));
    expect(track.mock.calls.filter((c) => c[0] === "audio_play")).toHaveLength(1);
  });

  it("播完记 audio_complete —— 这是「真的在听」的唯一硬信号", async () => {
    const el = await start();
    act(() => void el.dispatchEvent(new Event("ended")));
    expect(track).toHaveBeenCalledWith("audio_complete", { text_id: 9, juan_num: 1 });
  });

  it("拖动进度条记 audio_seek", async () => {
    await start();
    await userEvent.click(screen.getByText("jump"));
    expect(track).toHaveBeenCalledWith("audio_seek", { text_id: 9, juan_num: 1 });
  });

  it("一次拖动只记一条 —— antd Slider 的 onChange 连发，不节流会淹没其他事件", async () => {
    // 生产实测：仅仅 mousedown→mousemove→mouseup 就发了 2 条；
    // 真人横拖整条进度条会发几十条，audio_seek 会把 open/play/complete 全压下去。
    await start();
    const jump = screen.getByText("jump");
    await userEvent.click(jump);
    await userEvent.click(jump);
    await userEvent.click(jump);
    expect(track.mock.calls.filter((c) => c[0] === "audio_seek")).toHaveLength(1);
  });

  it("隔开足够久的两次拖动记两条 —— 节流不能把真实的第二次跳播吃掉", async () => {
    const now = vi.spyOn(Date, "now");
    now.mockReturnValue(1_000_000);
    await start();
    await userEvent.click(screen.getByText("jump"));
    now.mockReturnValue(1_000_000 + 5_000);
    await userEvent.click(screen.getByText("jump"));
    expect(track.mock.calls.filter((c) => c[0] === "audio_seek")).toHaveLength(2);
  });

  it("没有曲目时 seek 不记事件", async () => {
    render(
      <AudioPlayerProvider>
        <Harness />
      </AudioPlayerProvider>,
    );
    await userEvent.click(screen.getByText("jump"));
    expect(track).not.toHaveBeenCalled();
  });
});
