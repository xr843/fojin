import dynastyEn from "../content/dynastyLocales/en.json";
import dynastyZhHant from "../content/dynastyLocales/zh-Hant.json";
import dynastyZh from "../content/dynastyLocales/zh.json";

export interface DynastyPeriod {
  key: string;
  name_zh: string;
  name_en: string;
  name: string;
  start: number;
  end: number;
  color: string;
}

interface DynastyLocalePeriod {
  canonical: string;
  name: string;
}

interface DynastyLocaleData {
  periods: Record<string, DynastyLocalePeriod>;
  aliases: Record<string, string>;
}

type SupportedDynastyLocale = "zh" | "zh-Hant" | "en";

const DYNASTY_LOCALES: Record<SupportedDynastyLocale, DynastyLocaleData> = {
  en: dynastyEn,
  zh: dynastyZh,
  "zh-Hant": dynastyZhHant,
};

const BASE_DYNASTIES = [
  { key: "pre_qin", start: -770, end: -221, color: "#8b7355" },
  { key: "qin", start: -221, end: -206, color: "#4a4a4a" },
  { key: "western_han", start: -206, end: 8, color: "#c75450" },
  { key: "eastern_han", start: 25, end: 220, color: "#d4756b" },
  { key: "three_kingdoms", start: 220, end: 280, color: "#6b8e5b" },
  { key: "western_jin", start: 265, end: 316, color: "#7a9e6a" },
  { key: "eastern_jin", start: 317, end: 420, color: "#8aae7a" },
  { key: "sixteen_kingdoms", start: 304, end: 439, color: "#9b8b6e" },
  { key: "southern_dynasties", start: 420, end: 589, color: "#b08d57" },
  { key: "northern_dynasties", start: 386, end: 581, color: "#a07d47" },
  { key: "sui", start: 581, end: 618, color: "#4a7c9b" },
  { key: "tang", start: 618, end: 907, color: "#c75450" },
  { key: "five_dynasties", start: 907, end: 960, color: "#8b6e5b" },
  { key: "northern_song", start: 960, end: 1127, color: "#4a7c9b" },
  { key: "southern_song", start: 1127, end: 1279, color: "#5a8cab" },
  { key: "liao", start: 916, end: 1125, color: "#7a6e5b" },
  { key: "jin_jurchen", start: 1115, end: 1234, color: "#b08d57" },
  { key: "yuan", start: 1271, end: 1368, color: "#4a6a4a" },
  { key: "ming", start: 1368, end: 1644, color: "#8b2500" },
  { key: "qing", start: 1644, end: 1912, color: "#b08d57" },
  { key: "modern", start: 1912, end: 2000, color: "#4a4a4a" },
  { key: "india", start: -500, end: 1200, color: "#d4a56a" },
  { key: "japan", start: 600, end: 1900, color: "#c75480" },
  { key: "korea", start: 918, end: 1910, color: "#5470c6" },
  { key: "tibet", start: 600, end: 1900, color: "#91cc75" },
] as const;

const localizedDynastyCache = new Map<SupportedDynastyLocale, DynastyPeriod[]>();

function dynastyLocaleFor(language: string | undefined): SupportedDynastyLocale {
  if (!language) return "zh";
  if (language.startsWith("zh-Hant") || language.startsWith("zh-TW") || language.startsWith("zh-HK")) {
    return "zh-Hant";
  }
  if (language.startsWith("en")) return "en";
  return "zh";
}

function periodLocale(key: string, locale: SupportedDynastyLocale): DynastyLocalePeriod {
  return DYNASTY_LOCALES[locale].periods[key] ?? DYNASTY_LOCALES.zh.periods[key];
}

export function getLocalizedDynasties(language = "zh"): DynastyPeriod[] {
  const locale = dynastyLocaleFor(language);
  const cached = localizedDynastyCache.get(locale);
  if (cached) return cached;

  const dynasties = BASE_DYNASTIES.map((period) => {
    const zhPeriod = periodLocale(period.key, "zh");
    const enPeriod = periodLocale(period.key, "en");
    const localizedPeriod = periodLocale(period.key, locale);

    return {
      ...period,
      name_zh: zhPeriod.canonical,
      name_en: enPeriod.name,
      name: localizedPeriod.name,
    };
  });

  localizedDynastyCache.set(locale, dynasties);
  return dynasties;
}

export const DYNASTIES: DynastyPeriod[] = getLocalizedDynasties("zh");

const ALIASES: Record<string, string> = dynastyZh.aliases;

const BY_NAME = new Map(DYNASTIES.map((d) => [d.name_zh, d]));

export function resolveDynasty(nameZh: string | null | undefined): DynastyPeriod | undefined {
  if (!nameZh) return undefined;
  const canonical = ALIASES[nameZh] ?? nameZh;
  return BY_NAME.get(canonical);
}

export function getDynastyLabel(nameZh: string | null | undefined, language = "zh"): string {
  if (!nameZh) return "";
  const resolved = resolveDynasty(nameZh);
  if (!resolved) return nameZh;

  return getLocalizedDynasties(language).find((dynasty) => dynasty.key === resolved.key)?.name ?? resolved.name;
}
