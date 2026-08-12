import { createContext, useContext } from "react";

import type { TextAudioResponse } from "../api/client";

export interface AudioTrack {
  textId: number;
  juanNum: number;
  /** 经名 + 卷次，用于锁屏 MediaSession 与播放条标题 */
  title: string;
  audio: TextAudioResponse;
}

export interface AudioPlayerState {
  track: AudioTrack | null;
  playing: boolean;
  /** 当前 cue 下标，-1 表示尚未进入任何片段 */
  cueIndex: number;
  rate: number;
  /** 已播毫秒数，供进度条显示 */
  positionMs: number;
  play(track: AudioTrack): void;
  toggle(): void;
  seek(ms: number): void;
  setRate(rate: number): void;
  stop(): void;
}

export const AudioPlayerContext = createContext<AudioPlayerState | null>(null);

/**
 * 读诵播放器状态。
 *
 * Provider 挂在 Layout 层（不在阅读页），所以切卷时 <audio> 不重挂载、
 * 播放不中断 —— 跨卷连续播放是「听经」场景的刚需。
 *
 * 未包在 Provider 内时返回惰性空态，调用方无需判空。
 */
export function useAudioPlayer(): AudioPlayerState {
  const ctx = useContext(AudioPlayerContext);
  if (ctx) return ctx;
  return {
    track: null,
    playing: false,
    cueIndex: -1,
    rate: 1,
    positionMs: 0,
    play: () => {},
    toggle: () => {},
    seek: () => {},
    setRate: () => {},
    stop: () => {},
  };
}
