import { Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { DictConceptResponse } from "../api/client";

const LANG_COLORS: Record<string, string> = {
  zh: "red",
  sa: "orange",
  pi: "green",
  bo: "blue",
  en: "purple",
};

const LANG_LABEL_KEYS: Record<string, string> = {
  zh: "lang.zh",
  sa: "lang.sa",
  pi: "lang.pi",
  bo: "lang.bo",
  en: "lang.en",
};

interface Props {
  data: DictConceptResponse | undefined;
  /** Search a picked word form (e.g. clicking the Sanskrit form). */
  onPick: (term: string) => void;
}

/**
 * Multilingual concept header shown above dictionary search results when the
 * query resolves to a cross-lingual term concept (汉 涅槃 · 梵 nirvāṇa · 巴
 * nibbāna · 藏 …). Renders nothing when no concept matched, so the page falls
 * back to plain grouped results.
 */
export default function ConceptCard({ data, onPick }: Props) {
  const { t } = useTranslation();
  const concept = data?.concept;
  if (!concept) return null;

  // Ordered (lang, form) pairs for the forms that exist on this concept.
  const forms: Array<{ lang: string; value: string }> = [
    { lang: "zh", value: concept.chinese ?? "" },
    { lang: "sa", value: concept.sanskrit ?? "" },
    { lang: "pi", value: concept.pali ?? "" },
    { lang: "bo", value: concept.tibetan ?? "" },
    { lang: "en", value: concept.english ?? "" },
  ].filter((f) => f.value);

  if (forms.length < 2) return null; // need ≥2 languages to be worth a card

  return (
    <div className="dict-concept-card">
      <div className="dict-concept-card-label">{t("dict.concept.title")}</div>
      <div className="dict-concept-forms">
        {forms.map(({ lang, value }) => (
          <button
            key={lang}
            type="button"
            className="dict-concept-form"
            onClick={() => onPick(value)}
            title={t("dict.concept.search_form")}
          >
            <Tag color={LANG_COLORS[lang]} style={{ margin: 0, fontSize: 11 }}>
              {t(LANG_LABEL_KEYS[lang])}
            </Tag>
            <span className="dict-concept-form-text" lang={lang}>
              {value}
            </span>
          </button>
        ))}
      </div>
      {concept.devanagari && (
        <div className="dict-concept-devanagari" lang="sa">
          {concept.devanagari}
        </div>
      )}
    </div>
  );
}
