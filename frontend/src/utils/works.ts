import type { WorkWitnessInfo } from "../api/client";
import type { TFunction } from "i18next";

/** Witness language code → i18n key. */
export const WORK_LANG_LABEL_KEYS: Record<string, string> = {
  lzh: "work.lang.zh",
  zh: "work.lang.zh",
  pi: "work.lang.pi",
  pli: "work.lang.pi",
  sa: "work.lang.sa",
  san: "work.lang.sa",
  bo: "work.lang.bo",
  tib: "work.lang.bo",
  en: "work.lang.en",
};

/** Witness canon code → i18n key for common collections; unknown values hide. */
export const WORK_CANON_LABEL_KEYS: Record<string, string> = {
  taisho: "work.canon.taisho",
  xuzangjing: "work.canon.xuzang",
  xuzang: "work.canon.xuzang",
  pali: "work.canon.pali",
  kangyur: "work.canon.kangyur",
  gretil: "work.canon.gretil",
};

export function workLangLabel(lang: string, t?: TFunction): string {
  const key = WORK_LANG_LABEL_KEYS[lang];
  return key && t ? t(key) : key || lang;
}

export function workCanonLabel(canon: string | null | undefined, t?: TFunction): string | null {
  if (!canon) return null;
  const key = WORK_CANON_LABEL_KEYS[canon];
  return key && t ? t(key) : key || null;
}

/** 见证本的阅读链接：有正文进阅读器，否则进详情页。 */
export function witnessHref(w: Pick<WorkWitnessInfo, "text_id" | "has_content">): string {
  return w.has_content ? `/texts/${w.text_id}/read` : `/texts/${w.text_id}`;
}
