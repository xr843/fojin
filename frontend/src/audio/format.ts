/** 毫秒 → `1:41` / `2:14:00`。语言中立，不进 i18n。 */
export function formatDuration(ms: number): string {
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  // 一小时以上必须补上小时位 —— 壇經一卷 134 分钟，写成「134:00」没人看得懂。
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}
