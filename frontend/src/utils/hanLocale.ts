/**
 * Which Han script a UI language reads in — split out of hanScript.ts so pages
 * that only need the decision (e.g. HomePage, eager-loaded) don't pull in the
 * 1.2 MB OpenCC dictionary that hanScript.ts imports.
 */
export type HanScript = "simplified" | "traditional";

/**
 * The traditional-script locales, mirroring `normalizeCollectionLocale` in
 * data/collections.ts. Everything else — including `en`, whose curated titles
 * are simplified Chinese — renders simplified.
 */
export function scriptForLanguage(language: string): HanScript {
  if (
    language.startsWith("zh-Hant") ||
    language.startsWith("zh-TW") ||
    language.startsWith("zh-HK")
  ) {
    return "traditional";
  }
  return "simplified";
}
