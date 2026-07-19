/**
 * Render Han text in the script the UI language asks for.
 *
 * Backend text titles (`title_zh`) are passed through from CBETA, which stores
 * traditional Chinese, while the hand-curated page copy is written per locale.
 * Rendering the upstream string verbatim put 大方廣佛華嚴經 directly under
 * 华严经系列 for 中文简体 readers — the corpus's script leaking into the UI.
 * The script a title renders in should follow the reader's language.
 *
 * Conversion is OpenCC's 1 char → 1 char mapping (same lib the citation matcher
 * already folds with), so offsets are preserved and non-Han text is untouched.
 */
import * as OpenCC from "opencc-js";

export type HanScript = "simplified" | "traditional";

const toSimplified = OpenCC.Converter({ from: "tw", to: "cn" });
const toTraditional = OpenCC.Converter({ from: "cn", to: "tw" });

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

/** Convert `text` into the Han script matching `language`. */
export function localizeHan(text: string, language: string): string {
  if (!text) return text;
  try {
    return scriptForLanguage(language) === "traditional"
      ? toTraditional(text)
      : toSimplified(text);
  } catch {
    // Never let a converter hiccup blank out a title.
    return text;
  }
}
