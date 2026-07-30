/**
 * Is a scroll container close enough to its bottom that new content should
 * auto-follow?
 *
 * Lives here rather than in ChatPage so it can be unit-tested without ChatPage
 * exporting a non-component (which trips `react-refresh/only-export-components`
 * — a CI error, the frontend lint gate runs `--max-warnings 0`).
 *
 * 80px 的容差不是随手取的，也别调小 —— 一个严格的 `=== 0` 判据会在下列情形把
 * 「用户仍在底部」误判成「用户已离开」，从而关掉自动跟随：
 *
 *   - 分数设备像素与缩放会让 `scrollHeight - scrollTop - clientHeight` 停在
 *     0.5 这类非零残值上；
 *   - 流式内容在「滚动落地」与「下一块内容插入」之间有一帧的时间差，那一帧里
 *     距底就是刚插入内容的高度；
 *   - 用户可能只是把滚轮往上拨了一格又想继续跟读。
 */
export const NEAR_BOTTOM_PX = 80;

export function isNearBottom(
  el: Pick<HTMLElement, "scrollHeight" | "scrollTop" | "clientHeight"> | null,
): boolean {
  // No element yet (first render) counts as "at bottom" so the very first
  // token of a fresh answer still scrolls into view.
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
}
