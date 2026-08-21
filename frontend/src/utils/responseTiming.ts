/**
 * 回答耗时的显示格式。
 *
 * 一位小数只在 60 秒以内保留：短的那些差半秒是能感觉到的，而「共 182.0 秒」
 * 里那个 .0 只是噪音。取整用四舍五入而不是截断 —— 59.97 秒该读作 60.0 秒，
 * 不该读作 59.9 秒。
 */
export function formatResponseSeconds(ms: number): string {
  const s = ms / 1000;
  return s < 60 ? (Math.round(s * 10) / 10).toFixed(1) : String(Math.round(s));
}
