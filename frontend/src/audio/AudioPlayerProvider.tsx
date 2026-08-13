import { useState, useRef, useEffect, useCallback, useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { findCueIndex } from "./cues";
import { trackAudio } from "./telemetry";
import { AudioPlayerContext, type AudioPlayerState, type AudioTrack } from "./useAudioPlayback";

/** 同一次拖动内 audio_seek 的最小间隔。见 seek() 里的说明。 */
const SEEK_TRACK_GAP_MS = 2000;

/**
 * 读诵播放器。挂在 Layout 层，持有全站唯一的 <audio>。
 *
 * ⚠️ 不要把它下放到阅读页：切卷会重挂载页面组件，跨卷连续播放会断 ——
 *    而连续播放正是「听经」场景的刚需。
 *
 * 刻意不在这里渲染 PlayerBar —— Provider 只管状态，UI 由 Layout 并列挂载，
 * 两者互不 import，各自可独立测试。
 */
export default function AudioPlayerProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // 已记过 audio_play 的曲目键。暂停后续播会再次触发 play 事件，
  // 不去重的话「有多少人开始听」会被续播灌水。
  const playedRef = useRef<string | null>(null);
  const lastSeekTrackedRef = useRef(0);
  const [track, setTrack] = useState<AudioTrack | null>(null);
  const [playing, setPlaying] = useState(false);
  const [cueIndex, setCueIndex] = useState(-1);
  const [positionMs, setPositionMs] = useState(0);
  const [rate, setRateState] = useState(1);

  // ⚠️ 必须在 effect 里建，不能在 render 期间碰 ref ——
  //    React Compiler 会直接报 "Cannot access refs during render"。
  useEffect(() => {
    if (audioRef.current === null && typeof Audio !== "undefined") {
      audioRef.current = new Audio();
      audioRef.current.preload = "metadata";
    }
    const el = audioRef.current;
    return () => {
      el?.pause();
    };
  }, []);

  const play = useCallback((next: AudioTrack) => {
    const el = audioRef.current;
    if (!el) return;
    if (el.dataset.src !== next.audio.url) {
      el.src = next.audio.url;
      el.dataset.src = next.audio.url;
      setCueIndex(-1);
      setPositionMs(0);
    }
    setTrack(next);
    // iOS 要求播放由用户手势同步触发 —— 本函数只在按钮 onClick 里调用。
    void el.play().catch(() => setPlaying(false));
  }, []);

  const toggle = useCallback(() => {
    const el = audioRef.current;
    if (!el || !track) return;
    if (el.paused) void el.play().catch(() => setPlaying(false));
    else el.pause();
  }, [track]);

  const seek = useCallback(
    (ms: number) => {
      const el = audioRef.current;
      if (el) el.currentTime = ms / 1000;
      if (!track) return;
      // ⚠️ antd Slider 的 onChange 在拖动过程中连发 —— 生产实测一次
      //    mousedown→mousemove→mouseup 就发了 2 条，真人横拖整条进度条会发
      //    几十条。不节流的话 audio_seek 会把 open/play/complete 全淹没，
      //    Umami 面板上看起来像"用户主要在拖进度条"。
      const now = Date.now();
      if (now - lastSeekTrackedRef.current < SEEK_TRACK_GAP_MS) return;
      lastSeekTrackedRef.current = now;
      trackAudio("audio_seek", track.textId, track.juanNum);
    },
    [track],
  );

  const setRate = useCallback((r: number) => {
    const el = audioRef.current;
    if (el) el.playbackRate = r;
    setRateState(r);
  }, []);

  const stop = useCallback(() => {
    const el = audioRef.current;
    if (el) {
      el.pause();
      el.removeAttribute("src");
      delete el.dataset.src;
      el.load();
    }
    setTrack(null);
    setPlaying(false);
    setCueIndex(-1);
    setPositionMs(0);
    // 关掉播放器再重开同一卷算一次新的收听
    playedRef.current = null;
  }, []);

  // 播放状态与 cue 跟随
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onPlay = () => {
      setPlaying(true);
      if (!track) return;
      const key = `${track.textId}/${track.juanNum}`;
      if (playedRef.current === key) return;   // 续播不重复记
      playedRef.current = key;
      trackAudio("audio_play", track.textId, track.juanNum);
    };
    const onPause = () => setPlaying(false);
    const onEnded = () => {
      setPlaying(false);
      if (track) trackAudio("audio_complete", track.textId, track.juanNum);
    };
    const onTime = () => {
      const ms = Math.round(el.currentTime * 1000);
      setPositionMs(ms);
      if (!track) return;
      const idx = findCueIndex(track.audio.cues, ms);
      setCueIndex((prev) => (prev === idx ? prev : idx));
    };
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnded);
    el.addEventListener("timeupdate", onTime);
    return () => {
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnded);
      el.removeEventListener("timeupdate", onTime);
    };
  }, [track]);

  // 锁屏 / 通知栏控制。artist 固定标注「AI 合成朗读」——
  // 锁屏也是面向用户的位置，同样不得让人以为是法师读诵。
  useEffect(() => {
    if (!("mediaSession" in navigator) || !track) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: t("reader.audio.synthetic_label"),
      album: t("reader.audio.album"),
    });
    navigator.mediaSession.setActionHandler("play", () => toggle());
    navigator.mediaSession.setActionHandler("pause", () => toggle());
    return () => {
      navigator.mediaSession.setActionHandler("play", null);
      navigator.mediaSession.setActionHandler("pause", null);
    };
  }, [track, toggle, t]);

  const value = useMemo<AudioPlayerState>(
    () => ({ track, playing, cueIndex, rate, positionMs, play, toggle, seek, setRate, stop }),
    [track, playing, cueIndex, rate, positionMs, play, toggle, seek, setRate, stop],
  );

  return <AudioPlayerContext.Provider value={value}>{children}</AudioPlayerContext.Provider>;
}
