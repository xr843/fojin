import { Tag } from "antd";
import { LinkOutlined, EyeOutlined } from "@ant-design/icons";
import { buildSearchUrl } from "../../utils/sourceUrls";
import type { DataSource } from "../../api/client";

export default function ExternalCard({ source, query, rank }: { source: DataSource; query: string; rank: number }) {
  const url = buildSearchUrl(source.code, query) || "#";
  return (
    <div className="s-card s-card-ext">
      <div className="s-card-rank">排序<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title">{query}</div>
        <div className="s-card-tags">
          <Tag color="blue" style={{ fontSize: 11 }}>{source.name_zh}</Tag>
          <Tag style={{ fontSize: 11 }}>外链跳转</Tag>
          {source.region && <Tag style={{ fontSize: 11 }}>{source.region}</Tag>}
        </div>
        <div className="s-card-meta">
          <span>馆藏: {source.name_zh}</span>
        </div>
        <div className="s-card-actions">
          <a className="s-card-btn-primary" href={url} target="_blank" rel="noopener noreferrer"
            aria-label={`前往 ${source.name_zh} 搜索 ${query}`}>
            <LinkOutlined /> 前往原站搜索
          </a>
          {source.base_url && (
            <a className="s-card-btn" href={source.base_url} target="_blank" rel="noopener noreferrer"
              aria-label={`访问 ${source.name_zh} 主页`}>
              <EyeOutlined /> 访问主页
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
