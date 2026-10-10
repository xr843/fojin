import { useMemo } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Tag } from "antd";
import { TranslationOutlined } from "@ant-design/icons";
import BookmarkButton from "../BookmarkButton";
import { sanitizeHighlight } from "../../utils/sanitize";
import { getSourceLabel } from "../../utils/sourceUrls";
import { getAlignmentCatalog, type SearchHit } from "../../api/client";

// lzh/zh both render as Classical Chinese — see lang.* keys in translation.json
const LANG_KEYS: Record<string, string> = {
  lzh: "lang.lzh",
  zh: "lang.lzh",
  pi: "lang.pi",
  en: "lang.en",
  bo: "lang.bo",
  sa: "lang.sa",
};

export default function ResultCard({ hit }: { hit: SearchHit }) {
  const { t } = useTranslation();
  const titleHtml = hit.highlight?.title_zh?.[0] ?? hit.title_zh;
  const sourceName = hit.source_code ? getSourceLabel(hit.source_code, t) : null;
  const relatedTranslations = hit.related_translations || [];
  const langLabel = (lang: string) => (LANG_KEYS[lang] ? t(LANG_KEYS[lang]) : lang);

  // Badge texts that have cross-canon (藏/梵) parallels. Reuses the cached
  // alignment catalog (one fetch per session, shared with the collections card
  // and the text-detail entry); clicking the card lands on the detail page where
  // the prominent CrossCanonEntry card opens the reader's parallel view.
  const { data: catalog } = useQuery({
    queryKey: ["alignmentCatalog"],
    queryFn: getAlignmentCatalog,
    staleTime: 3600_000,
    retry: 1,
  });
  const hasCrossCanon = useMemo(
    () => !!catalog && catalog.entries.some((e) => e.text_id === hit.id),
    [catalog, hit.id],
  );

  return (
    <div className="s-card">
      <div className="s-card-body">
        {/* 经名即去详情页的主链接（整张卡唯一的视觉重点）；原先的实心「查看详情」已去掉 */}
        <div className="s-card-title">
          <Link to={`/texts/${hit.id}`} className="s-card-title-link">
            <span dangerouslySetInnerHTML={{ __html: sanitizeHighlight(titleHtml) }} />
          </Link>
        </div>
        <div className="s-card-tags">
          {sourceName && (
            <Tag color="volcano" style={{ fontSize: 11 }}>{sourceName}</Tag>
          )}
          <Tag style={{ fontSize: 11 }}>{hit.has_content ? t("search.local_fulltext") : t("search.catalog_data")}</Tag>
          {hasCrossCanon && (
            <Tag color="cyan" style={{ fontSize: 11 }}>{t("crosscanon.entry_title")}</Tag>
          )}
          {hit.category && <Tag style={{ fontSize: 11 }}>{hit.category}</Tag>}
          {hit.lang && hit.lang !== "lzh" && (
            <Tag style={{ fontSize: 11 }}>
              {langLabel(hit.lang)}
            </Tag>
          )}
        </div>
        <div className="s-card-meta">
          {hit.translator && (
            <span>{t("search.translator_label")}: {hit.dynasty ? `[${hit.dynasty}] ` : ""}{hit.translator}</span>
          )}
        </div>
        <div className="s-card-meta">
          <span>{t("search.cbeta_id_label")}: {hit.cbeta_id}</span>
        </div>
        {hit.highlight && Object.entries(hit.highlight).filter(([k]) => k !== "title_zh").map(([field, fragments]) => (
          <div key={field} className="s-card-preview" dangerouslySetInnerHTML={{
            __html: sanitizeHighlight(fragments[0]),
          }} />
        ))}
        {relatedTranslations.length > 0 && (
          <div className="s-card-translations">
            <TranslationOutlined style={{ fontSize: 12, color: "var(--fj-ink-muted)", marginRight: 4 }} />
            <span style={{ fontSize: 12, color: "var(--fj-ink-muted)", marginRight: 6 }}>{t("search.other_versions")}</span>
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
        {/* 游客看不到收藏（BookmarkButton 返回 null），此时整行由 .s-card-actions:empty 收起 */}
        <div className="s-card-actions">
          <BookmarkButton textId={hit.id} size="small" />
        </div>
      </div>
    </div>
  );
}
