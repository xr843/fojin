import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Tag, Button } from "antd";
import { LinkOutlined } from "@ant-design/icons";
import { sanitizeHighlight } from "../../utils/sanitize";
import { buildCbetaReadUrl } from "../../utils/sourceUrls";
import type { ContentSearchHit } from "../../api/client";

const LANG_KEYS: Record<string, string> = {
  pi: "lang.pi",
  en: "lang.en",
  bo: "lang.bo",
  sa: "lang.sa",
};

export default function ContentCard({ hit, rank }: { hit: ContentSearchHit; rank: number }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const hasMore = hit.matched_juan_count > 1;
  const cbetaUrl = buildCbetaReadUrl(hit.cbeta_id);

  return (
    <div className="s-card">
      <div className="s-card-rank">#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title">{hit.title_zh}</div>
        <div className="s-card-tags">
          <Tag style={{ fontSize: 11 }}>{hit.cbeta_id}</Tag>
          {hit.translator && <Tag style={{ fontSize: 11 }}>{hit.dynasty ? `[${hit.dynasty}] ` : ""}{hit.translator}</Tag>}
          {hit.lang && hit.lang !== "lzh" && (
            <Tag color="blue" style={{ fontSize: 11 }}>
              {LANG_KEYS[hit.lang] ? t(LANG_KEYS[hit.lang]) : hit.lang}
            </Tag>
          )}
          <Tag color="orange" style={{ fontSize: 11 }}>{t("search.juan_match_count", { n: hit.matched_juan_count })}</Tag>
        </div>
        {/* 最佳匹配卷 */}
        <div className="s-content-juan">
          <div className="s-content-juan-label">{t("search.juan_best", { num: hit.juan_num })}</div>
          {hit.highlight.map((h, j) => (
            <div key={j} className="s-card-meta" style={{ lineHeight: 1.7 }}
              dangerouslySetInnerHTML={{ __html: `...${sanitizeHighlight(h)}...` }} />
          ))}
          {cbetaUrl && (
            <Button type="primary" size="small" icon={<LinkOutlined />}
              style={{ background: "#8b2500", borderColor: "#8b2500", marginTop: 6 }}
              href={cbetaUrl} target="_blank" rel="noopener noreferrer">
              {t("search.cbeta_read")}
            </Button>
          )}
        </div>
        {/* 展开其他匹配卷 */}
        {hasMore && expanded && hit.matched_juans
          .filter((j) => j.juan_num !== hit.juan_num)
          .map((j) => (
            <div key={j.juan_num} className="s-content-juan">
              <div className="s-content-juan-label">{t("search.juan_n", { num: j.juan_num })}</div>
              {j.highlight.map((h, k) => (
                <div key={k} className="s-card-meta" style={{ lineHeight: 1.7 }}
                  dangerouslySetInnerHTML={{ __html: `...${sanitizeHighlight(h)}...` }} />
              ))}
            </div>
          ))}
        {hasMore && (
          <Button type="link" size="small" onClick={() => setExpanded(!expanded)}
            style={{ padding: 0, fontSize: 12, marginTop: 4 }}>
            {expanded ? t("search.collapse") : t("search.expand_juans", { n: hit.matched_juan_count - 1 })}
          </Button>
        )}
      </div>
    </div>
  );
}
