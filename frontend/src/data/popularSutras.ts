import sutrasEn from "../content/sutraLocales/en.json";
import sutrasZhHant from "../content/sutraLocales/zh-Hant.json";
import sutrasZh from "../content/sutraLocales/zh.json";

export interface SutraInfo {
  slug: string;
  cbeta_id: string;
  /** buddhist_texts.id - /texts/:id routes take the NUMERIC id, not cbeta_id */
  text_id: number;
  fascicle_count: number;
  title: string;
  alternateTitle: string;
  sanskritTitle: string;
  dynasty: string;
  translator: string;
  metaTitle: string;
  metaDescription: string;
  introduction: string[];
  keywords: string[];
}

interface SutraBase {
  slug: string;
  cbeta_id: string;
  text_id: number;
  fascicle_count: number;
}

interface SutraLocaleContent {
  title: string;
  alternateTitle: string;
  sanskritTitle: string;
  dynasty: string;
  translator: string;
  metaTitle: string;
  metaDescription: string;
  introduction: string[];
  keywords: string[];
}

type SutraLocaleMap = Record<string, SutraLocaleContent>;
type SutraLocaleKey = "en" | "zh" | "zh-Hant";

const SUTRA_BASE: SutraBase[] = [
  { slug: "heart-sutra", cbeta_id: "T0251", text_id: 9, fascicle_count: 1 },
  { slug: "diamond-sutra", cbeta_id: "T0235", text_id: 7, fascicle_count: 1 },
  { slug: "lotus-sutra", cbeta_id: "T0262", text_id: 6513, fascicle_count: 7 },
  { slug: "avatamsaka-sutra", cbeta_id: "T0279", text_id: 12, fascicle_count: 60 },
  { slug: "shurangama-sutra", cbeta_id: "T0945", text_id: 65, fascicle_count: 10 },
  { slug: "amitabha-sutra", cbeta_id: "T0366", text_id: 20, fascicle_count: 1 },
  { slug: "ksitigarbha-sutra", cbeta_id: "T0412", text_id: 24, fascicle_count: 2 },
  { slug: "medicine-buddha-sutra", cbeta_id: "T0450", text_id: 26, fascicle_count: 1 },
  { slug: "platform-sutra", cbeta_id: "T2008", text_id: 58, fascicle_count: 1 },
  { slug: "vimalakirti-sutra", cbeta_id: "T0475", text_id: 28, fascicle_count: 3 },
];

const SUTRA_LOCALES: Record<SutraLocaleKey, SutraLocaleMap> = {
  en: sutrasEn,
  zh: sutrasZh,
  "zh-Hant": sutrasZhHant,
};

function normalizeSutraLocale(language: string): SutraLocaleKey {
  if (language.startsWith("en")) return "en";
  if (
    language.startsWith("zh-Hant") ||
    language.startsWith("zh-TW") ||
    language.startsWith("zh-HK")
  ) {
    return "zh-Hant";
  }
  return "zh";
}

export function getLocalizedPopularSutras(language: string): SutraInfo[] {
  const locale = normalizeSutraLocale(language);
  const content = SUTRA_LOCALES[locale];
  const fallback = SUTRA_LOCALES.zh;

  return SUTRA_BASE.flatMap((sutra) => {
    const localized = content[sutra.slug] ?? fallback[sutra.slug];
    if (!localized) return [];

    return [
      {
        ...sutra,
        ...localized,
      },
    ];
  });
}

/** Find a sutra by slug. */
export function getSutraBySlug(slug: string, language = "zh"): SutraInfo | undefined {
  return getLocalizedPopularSutras(language).find((s) => s.slug === slug);
}

/** Get related sutras, excluding the current one. */
export function getRelatedSutras(slug: string, count = 4, language = "zh"): SutraInfo[] {
  return getLocalizedPopularSutras(language)
    .filter((s) => s.slug !== slug)
    .slice(0, count);
}

export const popularSutras: SutraInfo[] = getLocalizedPopularSutras("zh");
