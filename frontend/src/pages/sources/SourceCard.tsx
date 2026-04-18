import { Tag } from "antd";
import {
  ApiOutlined,
  FileImageOutlined,
  GlobalOutlined,
  LinkOutlined,
  ReadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import type { DataSource } from "../../api/client";
import { buildSearchUrlWithFallback, getLangName } from "../../utils/sourceUrls";
import { LANG_ORDER, getChannelLabel, trackSourceClick } from "./constants";

interface SourceCardProps {
  source: DataSource;
  searchQuery: string;
}

export default function SourceCard({ source: s, searchQuery }: SourceCardProps) {
  const langs = [
    ...new Map(
      (s.languages || "")
        .split(",")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => [getLangName(l), l] as const),
    ).values(),
  ].sort((a, b) => {
    const ia = LANG_ORDER.indexOf(a);
    const ib = LANG_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });

  const distributions = (s.distributions || []).filter((d) => d.is_active).slice(0, 5);
  const searchUrl = searchQuery
    ? buildSearchUrlWithFallback(s.code, s.base_url, searchQuery)
    : null;

  return (
    <div className="source-card">
      <div className="source-card-top">
        <span className="source-card-icon">
          <GlobalOutlined />
        </span>
        <div className="source-card-titles">
          <span className="source-card-name">{s.name_zh}</span>
          {s.name_en && <span className="source-card-name-en">{s.name_en}</span>}
        </div>
        <div className="source-card-badges">
          {s.has_local_fulltext && (
            <Tag color="green" className="source-card-badge">
              <ReadOutlined /> 已入库
            </Tag>
          )}
          {s.has_remote_fulltext && !s.has_local_fulltext && (
            <Tag color="cyan" className="source-card-badge">
              <ReadOutlined /> 外站全文
            </Tag>
          )}
          {s.supports_search && (
            <Tag color="blue" className="source-card-badge">
              <SearchOutlined /> 可搜索
            </Tag>
          )}
          {s.supports_iiif && (
            <Tag color="purple" className="source-card-badge">
              <FileImageOutlined /> 影像
            </Tag>
          )}
          {s.supports_api && (
            <Tag color="orange" className="source-card-badge">
              <ApiOutlined /> API
            </Tag>
          )}
        </div>
      </div>

      {s.description && <p className="source-card-desc">{s.description}</p>}

      {distributions.length > 0 && (
        <div className="source-card-dists">
          <div className="source-card-dists-title">官方分发端</div>
          <div className="source-card-dists-list">
            {distributions.map((d) => (
              <a
                key={d.code}
                href={d.url}
                target="_blank"
                rel="noopener noreferrer"
                className={`source-dist-link${d.is_primary_ingest ? " is-primary" : ""}`}
                title={d.license_note || d.name}
                onClick={() =>
                  trackSourceClick(s.code, "distribution", { dist: d.code })
                }
                onAuxClick={(e) => {
                  if (e.button === 1) {
                    trackSourceClick(s.code, "distribution", { dist: d.code });
                  }
                }}
              >
                <span className="source-dist-name">{d.name}</span>
                <span className="source-dist-meta">
                  {getChannelLabel(d.channel_type)}
                  {d.format ? ` · ${d.format}` : ""}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      <div className="source-card-langs">
        {langs.map((l) => (
          <span key={l} className="source-lang-tag">
            {getLangName(l)}
          </span>
        ))}
      </div>

      <div className="source-card-actions">
        {s.base_url && (
          <a
            href={s.base_url}
            target="_blank"
            rel="noopener noreferrer"
            className="source-btn"
            onClick={() => trackSourceClick(s.code, "visit")}
            onAuxClick={(e) => {
              if (e.button === 1) trackSourceClick(s.code, "visit");
            }}
          >
            <GlobalOutlined /> 访问网站
          </a>
        )}
        {searchUrl && (
          <a
            href={searchUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="source-btn source-btn-search"
            onClick={() =>
              trackSourceClick(s.code, "search", { query: searchQuery.slice(0, 30) })
            }
            onAuxClick={(e) => {
              if (e.button === 1) {
                trackSourceClick(s.code, "search", { query: searchQuery.slice(0, 30) });
              }
            }}
          >
            <LinkOutlined /> 搜索「{searchQuery}」
          </a>
        )}
      </div>
    </div>
  );
}
