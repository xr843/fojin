import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { currentUILang } from "../i18n";
import { langUrl, toSeoLang } from "./langUrl";

/**
 * canonical (self-referencing for the active UI language) + the four hreflang
 * alternates. Same rule as the server-side shells — see ./langUrl.ts.
 */
export function LangAlternates({ path }: { path: string }) {
  const { i18n } = useTranslation();
  const current = toSeoLang(currentUILang(i18n));
  return (
    <Helmet>
      <link rel="canonical" href={langUrl(path, current)} />
      <link rel="alternate" hrefLang="zh-Hans" href={langUrl(path, "zh")} />
      <link rel="alternate" hrefLang="zh-Hant" href={langUrl(path, "zh-Hant")} />
      <link rel="alternate" hrefLang="en" href={langUrl(path, "en")} />
      <link rel="alternate" hrefLang="x-default" href={langUrl(path, "zh")} />
    </Helmet>
  );
}
