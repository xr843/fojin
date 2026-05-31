import type { WorkWitnessInfo } from "../api/client";

/** 见证本语言 code → 中文标签 */
export const WORK_LANG_LABELS: Record<string, string> = {
  lzh: "中文",
  zh: "中文",
  pi: "巴利",
  pli: "巴利",
  sa: "梵文",
  san: "梵文",
  bo: "藏文",
  tib: "藏文",
  en: "英文",
};

/** 见证本藏经 code → 中文藏经名（仅常见者，未知返回 null 不展示） */
export const WORK_CANON_LABELS: Record<string, string> = {
  taisho: "大正藏",
  xuzangjing: "卍續藏",
  xuzang: "卍續藏",
  pali: "巴利",
  kangyur: "甘珠爾",
  gretil: "GRETIL",
};

export function workLangLabel(lang: string): string {
  return WORK_LANG_LABELS[lang] || lang;
}

export function workCanonLabel(canon: string | null | undefined): string | null {
  if (!canon) return null;
  return WORK_CANON_LABELS[canon] || null;
}

/** 见证本的阅读链接：有正文进阅读器，否则进详情页。 */
export function witnessHref(w: Pick<WorkWitnessInfo, "text_id" | "has_content">): string {
  return w.has_content ? `/texts/${w.text_id}/read` : `/texts/${w.text_id}`;
}
