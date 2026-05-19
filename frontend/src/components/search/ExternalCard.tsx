import { Tag } from "antd";
import { LinkOutlined, EyeOutlined } from "@ant-design/icons";
import { buildSearchUrl } from "../../utils/sourceUrls";
import type { DataSource } from "../../api/client";

/**
 * Compact single-row launcher for an external data source.
 *
 * Not a search result — it carries the current query into the source's
 * own search page. Deliberately low-chrome: source name + region + two
 * actions. The fake "排序 #N" rank, duplicate name tag, blanket "外链跳转"
 * tag and the "馆藏: {name}" line were dropped — they added no information.
 */
export default function ExternalCard({ source, query }: { source: DataSource; query: string }) {
  const url = buildSearchUrl(source.code, query) || "#";
  return (
    <div className="s-ext-row">
      <span className="s-ext-row-name">{source.name_zh}</span>
      {source.region && <Tag style={{ fontSize: 11, margin: 0 }}>{source.region}</Tag>}
      <span className="s-ext-row-spacer" />
      <a
        className="s-card-btn-primary"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`前往 ${source.name_zh} 搜索 ${query}`}
      >
        <LinkOutlined /> 前往原站搜索
      </a>
      {source.base_url && (
        <a
          className="s-card-btn"
          href={source.base_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`访问 ${source.name_zh} 主页`}
        >
          <EyeOutlined /> 访问主页
        </a>
      )}
    </div>
  );
}
