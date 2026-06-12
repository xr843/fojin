import i18n, { currentUILang } from "../i18n";

/**
 * Display name for a data source. Names are DB data, not translation keys:
 * name_zh is canonical, name_en covers 613/613 active sources after
 * migration 0154 (#707). English UI prefers name_en; zh / zh-Hant render
 * the canonical Chinese name.
 *
 * Call from inside a component that uses useTranslation() so a language
 * change re-renders the caller (this function itself is not reactive).
 */
export function localizedSourceName(s: { name_zh: string; name_en?: string | null }): string {
  return currentUILang(i18n) === "en" && s.name_en ? s.name_en : s.name_zh;
}
