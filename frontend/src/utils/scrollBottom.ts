/**
 * Is a scroll container close enough to its bottom that new content should
 * auto-follow?
 *
 * Lives here rather than in ChatPage so it can be unit-tested without ChatPage
 * exporting a non-component (which trips `react-refresh/only-export-components`
 * — a CI error, the frontend lint gate runs `--max-warnings 0`).
 *
 * The 80px tolerance is deliberately generous: `scrollIntoView({behavior:
 * "smooth"})` lands a few pixels short while the animation settles, and a
 * strict `=== 0` check would flip the caller to "user scrolled away" on its own
 * smooth scroll and then stop following its own stream.
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
