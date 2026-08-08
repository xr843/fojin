/**
 * 小津「随传承换装」的映射与配色。
 *
 * 原则（沿祖师长廊的无画像不变式）：**不画祖师本人**。小津代某位祖师作答时，
 * 换上那个传承的如法衣着——身份仍是小津（气泡里写着「正以 X 的口吻作答」），
 * 变的只是衣制。按传承 5 套，不按人 15 套。
 *
 * 映射关键词按生产 /api/chat/masters 的真实 tradition 字符串写成（2026-08-08
 * 实测 15 位）；后端加新祖师时若引入新传承词，落到 han 兜底，不会炸。
 */

export type AttireVariant = "han" | "indian" | "theravada" | "gelug" | "kagyu";

export function traditionToAttire(tradition: string | null | undefined): AttireVariant {
  const t = tradition ?? "";
  // 顺序有讲究：藏传三派先于「中观」——阿底峡（噶当）等藏传条目不含中观字样，
  // 但未来若出现「藏传·中观」应归藏传装。
  if (t.includes("南传")) return "theravada"; // i18n-exempt — 觉音 / 马哈希 / 阿姜查：偏袒右肩
  if (t.includes("格鲁") || t.includes("噶当")) return "gelug"; // i18n-exempt — 宗喀巴 / 阿底峡：黄班智达帽
  if (t.includes("噶举")) return "kagyu"; // i18n-exempt — 米拉日巴：白禅带
  if (t.includes("印度") || t.includes("中观")) return "indian"; // i18n-exempt — 龙树 / 鸠摩罗什：素赭袈裟
  return "han"; // 天台 / 禅 / 唯识 / 华严 / 净土 …：正金海青 + 赭红祖衣
}

/** 右键菜单里每位祖师名前的小色点（亮色端取袍色主调）。 */
export const ATTIRE_DOT: Record<AttireVariant, string> = {
  han: "#d6a13c",
  indian: "#a8763e",
  theravada: "#d97b29",
  gelug: "#e3b93d",
  kagyu: "#9c3f2f",
};
