import type { AudioCue } from "../api/client";

/**
 * 当前播放时间落在第几个 cue。早于首个 cue（含负数）与空数组返回 -1。
 *
 * 二分查找：一卷 13~600 个 cue，播放中 timeupdate 在部分浏览器可达 60Hz，
 * 线性扫描也够快，但二分是稳妥的默认。
 *
 * 边界语义：time_ms 恰等于某 cue 起点时归**该** cue（而非前一个），
 * 否则高亮会比声音慢一拍。
 */
export function findCueIndex(cues: AudioCue[], timeMs: number): number {
  let lo = 0;
  let hi = cues.length - 1;
  let hit = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (cues[mid].time_ms <= timeMs) {
      hit = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return hit;
}
