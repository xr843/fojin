import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Tag, Button } from "antd";
import { EyeOutlined, TranslationOutlined } from "@ant-design/icons";
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

const LANG_COLORS: Record<string, string> = {
  lzh: "red",
  zh: "red",
  pi: "orange",
  en: "blue",
  bo: "purple",
  sa: "green",
};

export default function ResultCard({ hit, rank }: { hit: SearchHit; rank: number }) {
  const navigate = useNavigate();
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
      <div className="s-card-rank">{t("search.rank")}<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title" dangerouslySetInnerHTML={{ __html: sanitizeHighlight(titleHtml) }} />
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
            <Tag color="blue" style={{ fontSize: 11 }}>
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
