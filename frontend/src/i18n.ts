import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import HttpBackend from "i18next-http-backend";
import LanguageDetector from "i18next-browser-languagedetector";
// Inline zh so the default language is available synchronously (no FOUT)
import zhTranslation from "../public/locales/zh/translation.json";

// UI locale codes — these own the `?lang=` query param (detector below).
// Text/source language FILTERS must use a different param (`tl`, see #709)
// and treat these codes as not-a-filter when reading legacy links.
export const SUPPORTED_UI_LANGS = ["zh", "zh-Hant", "en"] as const;

/**
 * The UI language to display/select in language pickers.
 *
 * Do NOT use i18n.resolvedLanguage for this: with partialBundledLanguages +
 * HttpBackend, a returning non-zh visitor inits before their locale file
 * arrives, so resolvedLanguage resolves to the zh fallback — and i18next only
 * recomputes it on changeLanguage, never on the later "loaded" event. The
 * header then renders an English UI with a「中文」label. i18n.language always
 * reflects the target language; we just normalize it onto our supported set.
 */
export function currentUILang(instance: typeof i18n = i18n): string {
  const lng = instance.language ?? "";
  if ((SUPPORTED_UI_LANGS as readonly string[]).includes(lng)) return lng;
  if (lng.startsWith("zh-Hant")) return "zh-Hant";
  const base = lng.split("-")[0];
  if ((SUPPORTED_UI_LANGS as readonly string[]).includes(base)) return base;
  return instance.resolvedLanguage ?? "zh";
}

i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "zh",
    supportedLngs: [...SUPPORTED_UI_LANGS],
    load: "currentOnly",
    keySeparator: false,
    nsSeparator: false,
    ns: ["translation"],
    defaultNS: "translation",
    resources: {
      zh: { translation: zhTranslation },
    },
    partialBundledLanguages: true,
    backend: {
      loadPath: "/locales/{{lng}}/translation.json",
    },
    detection: {
      order: ["querystring", "localStorage", "navigator"],
      lookupQuerystring: "lang",
      caches: ["localStorage"],
    },
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: false,
    },
  });

i18n.on("languageChanged", (lng) => {
  document.documentElement.lang = lng;
});

export default i18n;
