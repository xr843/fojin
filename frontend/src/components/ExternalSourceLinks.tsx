import { useState } from "react";
import { Typography } from "antd";
import { LinkOutlined, DownOutlined, UpOutlined } from "@ant-design/icons";
import type { DataSource } from "../api/client";
import { buildSearchUrl } from "../utils/sourceUrls";

interface ExternalSourceLinksProps {
  sources: DataSource[];
  query: string;
}

export default function ExternalSourceLinks({ sources, query }: ExternalSourceLinksProps) {
  const [expanded, setExpanded] = useState(false);

  if (!query || !sources || sources.length === 0) return null;

  const externalSources = sources.filter((s) => s.access_type === "external" && s.base_url);

  // Group by region. Only include sources with a registered direct-search
  // template; the previous Google site: fallback returned 0 results for
  // un-indexed mirror sites and misled users.
  const grouped: Record<string, Array<{ source: DataSource; url: string }>> = {};
  for (const s of externalSources) {
    const url = buildSearchUrl(s.code, query);
    if (!url) continue;
    const region = s.region || "其他";
    if (!grouped[region]) grouped[region] = [];
    grouped[region].push({ source: s, url });
  }

  const regionOrder = ["中国大陆", "中国台湾", "中国香港", "日本", "韩国", "国际", "美国", "英国", "德国", "法国", "印度"];
  const sortedRegions = Object.keys(grouped).sort((a, b) => {
    const ia = regionOrder.indexOf(a);
    const ib = regionOrder.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });

  const totalLinks = Object.values(grouped).reduce((s, arr) => s + arr.length, 0);
  const displayRegions = expanded ? sortedRegions : sortedRegions.slice(0, 4);

  return (
    <div className="ext-sources">
      <div className="ext-sources-header">
        <Typography.Text strong style={{ fontSize: 14, color: "#5c4f3d" }}>
          在外部数据源中搜索「{query}」
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
          {totalLinks} 个数据源可搜索
        </Typography.Text>
      </div>

      {displayRegions.map((region) => (
        <div key={region} className="ext-region">
          <div className="ext-region-label">
            {region}
            <span className="ext-region-count">{grouped[region].length}</span>
          </div>
          <div className="ext-region-links">
            {grouped[region].map(({ source, url }) => (
              <a
                key={source.code}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="ext-link"
              >
                <LinkOutlined />
                {source.name_zh}
              </a>
            ))}
          </div>
        </div>
      ))}

      {sortedRegions.length > 4 && (
        <button className="ext-toggle" onClick={() => setExpanded(!expanded)}>
          {expanded ? (
            <><UpOutlined /> 收起</>
          ) : (
            <><DownOutlined /> 展开全部 {sortedRegions.length} 个地区</>
          )}
        </button>
      )}
    </div>
  );
}
