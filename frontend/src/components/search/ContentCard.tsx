import { useState } from "react";
import { Tag, Button } from "antd";
import { LinkOutlined } from "@ant-design/icons";
import { sanitizeHighlight } from "../../utils/sanitize";
import { buildCbetaReadUrl } from "../../utils/sourceUrls";
import type { ContentSearchHit } from "../../api/client";

export default function ContentCard({ hit, rank }: { hit: ContentSearchHit; rank: number }) {
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
          <Tag color="orange" style={{ fontSize: 11 }}>{hit.matched_juan_count} 卷匹配</Tag>
        </div>
        {/* 最佳匹配卷 */}
        <div className="s-content-juan">
          <div className="s-content-juan-label">第{hit.juan_num}卷（最佳匹配）</div>
          {hit.highlight.map((h, j) => (
            <div key={j} className="s-card-meta" style={{ lineHeight: 1.7 }}
              dangerouslySetInnerHTML={{ __html: `...${sanitizeHighlight(h)}...` }} />
          ))}
          {cbetaUrl && (
            <Button type="primary" size="small" icon={<LinkOutlined />}
              style={{ background: "#8b2500", borderColor: "#8b2500", marginTop: 6 }}
              href={cbetaUrl} target="_blank" rel="noopener noreferrer">
              CBETA 阅读
            </Button>
          )}
        </div>
        {/* 展开其他匹配卷 */}
        {hasMore && expanded && hit.matched_juans
          .filter((j) => j.juan_num !== hit.juan_num)
          .map((j) => (
            <div key={j.juan_num} className="s-content-juan">
              <div className="s-content-juan-label">第{j.juan_num}卷</div>
              {j.highlight.map((h, k) => (
                <div key={k} className="s-card-meta" style={{ lineHeight: 1.7 }}
                  dangerouslySetInnerHTML={{ __html: `...${sanitizeHighlight(h)}...` }} />
              ))}
            </div>
          ))}
        {hasMore && (
          <Button type="link" size="small" onClick={() => setExpanded(!expanded)}
            style={{ padding: 0, fontSize: 12, marginTop: 4 }}>
            {expanded ? "收起" : `展开其他 ${hit.matched_juan_count - 1} 卷匹配`}
          </Button>
        )}
      </div>
    </div>
  );
}
