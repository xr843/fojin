import type { TFunction } from "i18next";

export function adminDateLocale(language: string): string {
  if (language.startsWith("zh-Hant")) return "zh-Hant";
  if (language.startsWith("en")) return "en-US";
  return "zh-CN";
}

export function formatAdminDate(value: string | null, language: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString(adminDateLocale(language), { hour12: false });
}

export function adminLabel(t: TFunction, key: string | undefined, fallback: string): string {
  if (!key) return fallback;
  return t(key, { defaultValue: fallback });
}
