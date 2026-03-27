import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import HttpBackend from "i18next-http-backend";
import LanguageDetector from "i18next-browser-languagedetector";
// Inline zh so the default language is available synchronously (no FOUT)
import zhTranslation from "../public/locales/zh/translation.json";

i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "zh",
    supportedLngs: ["zh", "en", "ja", "ko", "th", "vi", "si", "my"],
    load: "languageOnly",
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
