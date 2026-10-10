import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { Tag } from "antd";
import { TranslationOutlined } from "@ant-design/icons";
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

// en 不配色：antd 的 blue 不在站点色板内（#1300 已在其它页清掉），落到中性默认 Tag
const LANG_COLORS: Record<string, string> = {
  lzh: "red",
  zh: "red",
  pi: "orange",
  bo: "purple",
  sa: "green",
};

interface TitleEntry {
  lang: string;
  title: string;
  highlighted?: string;
}

export default function CrossLangCard({ hit }: { hit: CrossLanguageSearchHit }) {
  const { t } = useTranslation();
  const titleHtml = hit.highlight?.title_zh?.[0] ?? hit.title_zh;
  const sourceName = hit.source_code ? getSourceLabel(hit.source_code, t) : null;
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
      <div className="s-card-body">
        <div className="s-card-title">
          <Link to={`/texts/${hit.id}`} className="s-card-title-link">
            <span dangerouslySetInnerHTML={{ __html: sanitizeHighlight(titleHtml) }} />
          </Link>
        </div>
        {/* Show all available titles in other languages */}
        {titles.length > 0 && (
          <div className="s-card-alt-titles" style={{ marginBottom: 6 }}>
            {titles.map((entry) => (
              <div key={entry.lang} style={{ fontSize: 12, color: "var(--fj-ink-light)", lineHeight: 1.6 }}>
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
            <TranslationOutlined style={{ fontSize: 12, color: "var(--fj-ink-muted)", marginRight: 4 }} />
            <span style={{ fontSize: 12, color: "var(--fj-ink-muted)", marginRight: 6 }}>{t("search.related_translations")}</span>
            {/* 真链接而不是 Tag+onClick：Tab 可达、回车可跳、可新标签打开；外观仍是小标签，
                但允许折行——英文「Classical Chinese - …」在 320px 不再撑出整列。 */}
            {relatedTranslations.map((rt) => (
              <Link key={rt.id} to={`/texts/${rt.id}`} className="s-card-translation-link">
                {langLabel(rt.lang)}
                {rt.title ? ` - ${rt.title.length > 20 ? rt.title.slice(0, 20) + "..." : rt.title}` : ""}
              </Link>
            ))}
          </div>
        )}
        <div className="s-card-actions">
          <BookmarkButton textId={hit.id} size="small" />
        </div>
      </div>
    </div>
  );
}
