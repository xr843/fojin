/**
 * 读诵埋点。
 *
 * ⚠️ **只能在客户端埋。** `/audio/*.mp3` 带 `immutable, max-age=31536000`，
 * 绝大多数请求由 Cloudflare 边缘直接供给、永远到不了源站；宿主机 nginx 里
 * 那条 `access_log off` 就算打开，得到的也是严重低估的数字。
 *
 * 四个事件回答四个问题：
 * * `audio_open`     —— 有多少人**想**听（点了「读诵」）
 * * `audio_play`     —— 有多少人**开始**听（每卷只记一次，续播不灌水）
 * * `audio_complete` —— 有多少人**听完**了 ← 这是「真的在听」的唯一硬信号
 * * `audio_seek`     —— 有没有人在跳着听
 */
export type AudioEvent = "audio_open" | "audio_play" | "audio_complete" | "audio_seek";

export function trackAudio(event: AudioEvent, textId: number, juanNum: number): void {
  // 自托管者不配 VITE_UMAMI_* 就不会注入脚本（见 src/umami.ts）——
  // 埋点绝不能因此让播放器崩掉。
  if (typeof umami === "undefined") return;
  umami.track(event, { text_id: textId, juan_num: juanNum });
}
