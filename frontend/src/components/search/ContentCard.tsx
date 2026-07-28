import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Tag, Button } from "antd";
import { LinkOutlined, ReadOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { sanitizeHighlight } from "../../utils/sanitize";
import { buildCbetaReadUrl, buildReaderUrl } from "../../utils/sourceUrls";
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
          {/* 站内阅读器排在前面：它带标注、校勘、跨藏对照，CBETA 外链只作次要出口 */}
          <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
            <Link to={buildReaderUrl(hit.text_id, hit.juan_num)}>
              <Button type="primary" size="small" icon={<ReadOutlined />}
                style={{ background: "var(--fj-accent)", borderColor: "var(--fj-accent)" }}>
                {t("search.read")}
              </Button>
            </Link>
            {cbetaUrl && (
              <Button size="small" icon={<LinkOutlined />}
                href={cbetaUrl} target="_blank" rel="noopener noreferrer">
                {t("search.cbeta_read")}
              </Button>
            )}
          </div>
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
              <Link to={buildReaderUrl(hit.text_id, j.juan_num)}>
                <Button size="small" icon={<ReadOutlined />} style={{ marginTop: 6 }}>
                  {t("search.read")}
                </Button>
              </Link>
            </div>
          ))}
        {hasMore && (
          <Button type="link" size="small" onClick={() => setExpanded(!expanded)}
            // antd 会把 colorLink 当种子色再派生一遍，给什么值都不是最终色（暗色下
            // 派生成 #7eafdc，只有 4.32:1）。内联指定，跳过派生。
            style={{ padding: 0, fontSize: 12, marginTop: 4, color: "var(--fj-info)" }}>
            {expanded ? t("search.collapse") : t("search.expand_juans", { n: hit.matched_juan_count - 1 })}
          </Button>
        )}
      </div>
    </div>
  );
}
