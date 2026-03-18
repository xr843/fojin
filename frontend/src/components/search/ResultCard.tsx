import { useNavigate } from "react-router-dom";
import { Tag, Button } from "antd";
import { EyeOutlined, LinkOutlined } from "@ant-design/icons";
import BookmarkButton from "../BookmarkButton";
import { sanitizeHighlight } from "../../utils/sanitize";
import { getSourceLabel, buildCbetaReadUrl } from "../../utils/sourceUrls";
import type { SearchHit } from "../../api/client";

export default function ResultCard({ hit, rank }: { hit: SearchHit; rank: number }) {
  const navigate = useNavigate();
  const titleHtml = hit.highlight?.title_zh?.[0] ?? hit.title_zh;
  const sourceName = hit.source_code ? getSourceLabel(hit.source_code) : null;
  const cbetaUrl = buildCbetaReadUrl(hit.cbeta_id);

  return (
    <div className="s-card">
      <div className="s-card-rank">排序<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title" dangerouslySetInnerHTML={{ __html: sanitizeHighlight(titleHtml) }} />
        <div className="s-card-tags">
          {sourceName && (
            <Tag color="volcano" style={{ fontSize: 11 }}>{sourceName}</Tag>
          )}
          <Tag style={{ fontSize: 11 }}>{hit.has_content ? "本地全文" : "目录数据"}</Tag>
          {hit.category && <Tag style={{ fontSize: 11 }}>{hit.category}</Tag>}
          {hit.lang && hit.lang !== "lzh" && (
            <Tag color="blue" style={{ fontSize: 11 }}>
              {{ pi: "巴利文", en: "英文", bo: "藏文", sa: "梵文" }[hit.lang] || hit.lang}
            </Tag>
          )}
        </div>
        <div className="s-card-meta">
          {hit.translator && (
            <span>主要责任者: {hit.dynasty ? `[${hit.dynasty}] ` : ""}{hit.translator}</span>
          )}
        </div>
        <div className="s-card-meta">
          <span>编号: {hit.cbeta_id}</span>
        </div>
        {hit.highlight && Object.entries(hit.highlight).filter(([k]) => k !== "title_zh").map(([field, fragments]) => (
          <div key={field} className="s-card-preview" dangerouslySetInnerHTML={{
            __html: sanitizeHighlight(fragments[0]),
          }} />
        ))}
        <div className="s-card-actions">
          {cbetaUrl && (
            <Button type="primary" size="small" icon={<LinkOutlined />}
              style={{ background: "#8b2500", borderColor: "#8b2500" }}
              href={cbetaUrl} target="_blank" rel="noopener noreferrer">
              CBETA 阅读
            </Button>
          )}
          <Button size="small" icon={<EyeOutlined />}
            onClick={() => navigate(`/texts/${hit.id}`)}>
            查看详情
          </Button>
          <BookmarkButton textId={hit.id} size="small" />
        </div>
      </div>
    </div>
  );
}
