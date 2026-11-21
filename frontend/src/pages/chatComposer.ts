/**
 * 输入框行数。用户反馈（2026-11-21）：笔记本矮窗口里输入框太高，回答区被挤小。
 *
 * - 对话中默认 1 行，打字时随内容长高（autoSize）；空态首屏仍是 2 行 ——
 *   那时上方没有回答要看，输入框是主角。
 * - 矮屏（高度 ≤ 760px，常见 1366×768 笔记本减去浏览器栏后约 650）最多长到
 *   4 行，超出在框内滚动；高屏维持 8 行。
 */
export const COMPOSER_SHORT_VIEWPORT_QUERY = "(max-height: 760px)";

export function composerAutoSize(
  inConversation: boolean,
  shortViewport: boolean,
): { minRows: number; maxRows: number } {
  return {
    minRows: inConversation ? 1 : 2,
    maxRows: shortViewport ? 4 : 8,
  };
}
