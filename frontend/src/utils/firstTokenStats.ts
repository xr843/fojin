/** 本机最近几次「首字耗时」样本，给等待期一个诚实的预期（「上次首字约 N 秒」）。
 *
 *  只存本机 localStorage：这是这位用户在这个网络、这个模型上的经验值，比全站均值贴切；
 *  取中位数，一次 180 秒的极端值不该把预期拉到离谱。没有样本就返回 null——界面不显示，
 *  而不是显示一个编出来的数。 */
export const FIRST_TOKEN_SAMPLES_KEY = "fojin.chat.firstTokenMs";
const MAX_SAMPLES = 5;

function readSamples(): number[] {
  try {
    const raw = localStorage.getItem(FIRST_TOKEN_SAMPLES_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((n): n is number => typeof n === "number" && Number.isFinite(n) && n > 0)
      : [];
  } catch {
    return [];
  }
}

export function recordFirstTokenMs(ms: number): void {
  if (!Number.isFinite(ms) || ms <= 0) return;
  const next = [...readSamples(), ms].slice(-MAX_SAMPLES);
  try {
    localStorage.setItem(FIRST_TOKEN_SAMPLES_KEY, JSON.stringify(next));
  } catch {
    // 隐私模式 / 配额满：没有预期也不影响提问
  }
}

export function expectedFirstTokenSeconds(): number | null {
  const s = readSamples().sort((a, b) => a - b);
  if (s.length === 0) return null;
  const mid = Math.floor(s.length / 2);
  const median = s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
  return Math.max(1, Math.round(median / 1000));
}
