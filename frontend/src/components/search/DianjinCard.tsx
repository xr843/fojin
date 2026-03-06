import { Tag } from "antd";
import { LinkOutlined } from "@ant-design/icons";
import type { DianjinSearchHit } from "../../api/dianjin";

export default function DianjinCard({ hit, rank }: { hit: DianjinSearchHit; rank: number }) {
  return (
    <div className="s-card" style={{ borderLeft: "3px solid #1677ff" }}>
      <div className="s-card-rank">排序<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title">{hit.title || "无题"}</div>
        <div className="s-card-tags">
          <Tag color="blue" style={{ fontSize: 11 }}>典津</Tag>
          {hit.datasource_name && <Tag color="volcano" style={{ fontSize: 11 }}>{hit.datasource_name}</Tag>}
          {hit.collection && <Tag style={{ fontSize: 11 }}>{hit.collection}</Tag>}
          {hit.datasource_tags?.map((t) => (
            <Tag key={t} style={{ fontSize: 10 }}>{t}</Tag>
          ))}
        </div>
        <div className="s-card-meta">
          {hit.main_responsibility && <span>责任者: {hit.main_responsibility}</span>}
          {hit.edition && <span style={{ marginLeft: 12 }}>版本: {hit.edition}</span>}
        </div>
        <div className="s-card-actions">
          {hit.detail_url && (
            <a className="s-card-btn-primary" href={hit.detail_url} target="_blank" rel="noopener noreferrer">
              <LinkOutlined /> 前往典津查看
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
