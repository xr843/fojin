import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Tag, Button } from "antd";
import { EyeOutlined, TranslationOutlined } from "@ant-design/icons";
import BookmarkButton from "../BookmarkButton";
import { sanitizeHighlight } from "../../utils/sanitize";
import { getSourceLabel } from "../../utils/sourceUrls";
import type { CrossLanguageSearchHit } from "../../api/client";

// lzh/zh both render as Classical Chinese — see lang.* keys in translation.json
const LANG_KEYS: Record<string, string> = {
  lzh: "lang.lzh",
  zh: "lang.lzh",
  pi: "lang.pi",
  en: "lang.en",
  bo: "lang.bo",
  sa: "lang.sa",
};

const LANG_COLORS: Record<string, string> = {
  lzh: "red",
  zh: "red",
  pi: "orange",
  en: "blue",
  bo: "purple",
  sa: "green",
};

interface TitleEntry {
  lang: string;
  title: string;
  highlighted?: string;
}

export default function CrossLangCard({ hit, rank }: { hit: CrossLanguageSearchHit; rank: number }) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const titleHtml = hit.highlight?.title_zh?.[0] ?? hit.title_zh;
  const sourceName = hit.source_code ? getSourceLabel(hit.source_code) : null;
  const relatedTranslations = hit.related_translations || [];
  const langLabel = (lang: string) => (LANG_KEYS[lang] ? t(LANG_KEYS[lang]) : lang);

  // Collect all available titles for this text
  const titles: TitleEntry[] = [];
  if (hit.title_en) titles.push({ lang: "en", title: hit.title_en, highlighted: hit.highlight?.title_en?.[0] });
  if (hit.title_sa) titles.push({ lang: "sa", title: hit.title_sa, highlighted: hit.highlight?.title_sa?.[0] });
  if (hit.title_pi) titles.push({ lang: "pi", title: hit.title_pi, highlighted: hit.highlight?.title_pi?.[0] });
  if (hit.title_bo) titles.push({ lang: "bo", title: hit.title_bo, highlighted: hit.highlight?.title_bo?.[0] });

  return (
    <div className="s-card">
      <div className="s-card-rank">{t("search.rank")}<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title" dangerouslySetInnerHTML={{ __html: sanitizeHighlight(titleHtml) }} />
        {/* Show all available titles in other languages */}
        {titles.length > 0 && (
          <div className="s-card-alt-titles" style={{ marginBottom: 6 }}>
            {titles.map((entry) => (
              <div key={entry.lang} style={{ fontSize: 12, color: "#6b5e4d", lineHeight: 1.6 }}>
                <Tag color={LANG_COLORS[entry.lang] || "default"} style={{ fontSize: 10, padding: "0 4px", lineHeight: "18px" }}>
                  {langLabel(entry.lang)}
                </Tag>
                {entry.highlighted ? (
                  <span dangerouslySetInnerHTML={{ __html: sanitizeHighlight(entry.highlighted) }} />
                ) : (
                  <span>{entry.title}</span>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="s-card-tags">
          {sourceName && (
            <Tag color="volcano" style={{ fontSize: 11 }}>{sourceName}</Tag>
          )}
          <Tag style={{ fontSize: 11 }}>{hit.has_content ? t("search.local_fulltext") : t("search.catalog_data")}</Tag>
          {hit.category && <Tag style={{ fontSize: 11 }}>{hit.category}</Tag>}
          <Tag color={LANG_COLORS[hit.lang] || "default"} style={{ fontSize: 11 }}>
            {langLabel(hit.lang)}
          </Tag>
        </div>
        <div className="s-card-meta">
          {hit.translator && (
            <span>{t("search.translator_label")}: {hit.dynasty ? `[${hit.dynasty}] ` : ""}{hit.translator}</span>
          )}
        </div>
        <div className="s-card-meta">
          <span>{t("search.cbeta_id_label")}: {hit.cbeta_id}</span>
        </div>
        {relatedTranslations.length > 0 && (
          <div className="s-card-translations">
            <TranslationOutlined style={{ fontSize: 12, color: "#9a8e7a", marginRight: 4 }} />
            <span style={{ fontSize: 12, color: "#9a8e7a", marginRight: 6 }}>{t("search.related_translations")}</span>
            {relatedTranslations.map((rt) => (
              <Tag
                key={rt.id}
                color={LANG_COLORS[rt.lang] || "default"}
                style={{ fontSize: 11, cursor: "pointer", marginBottom: 2 }}
                onClick={() => navigate(`/texts/${rt.id}`)}
              >
                {langLabel(rt.lang)}
                {rt.title ? ` - ${rt.title.length > 20 ? rt.title.slice(0, 20) + "..." : rt.title}` : ""}
              </Tag>
            ))}
          </div>
        )}
        <div className="s-card-actions">
          <Button type="primary" size="small" icon={<EyeOutlined />}
            onClick={() => navigate(`/texts/${hit.id}`)}>
            {t("search.view_details")}
          </Button>
          <BookmarkButton textId={hit.id} size="small" />
        </div>
      </div>
    </div>
  );
}
