import { Tag, Tooltip } from "antd";
import {
  ApiOutlined,
  FileImageOutlined,
  GlobalOutlined,
  LinkOutlined,
  ReadOutlined,
  SearchOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import type { DataSource } from "../../api/client";
import { buildSearchUrl, getLangName } from "../../utils/sourceUrls";
import { LANG_ORDER, getChannelLabel, trackSourceClick } from "./constants";

interface SourceCardProps {
  source: DataSource;
  searchQuery: string;
}

// Cron-updated reachability verdicts worth surfacing to readers. "ok" shows
// nothing — only problems get a badge, to keep healthy cards uncluttered.
const HEALTH_BADGE: Record<
  Exclude<DataSource["health_status"], "ok">,
  { label: string; color: string; tip: string }
> = {
  degraded: {
    label: "访问受限",
    color: "gold",
    tip: "原站可达，但目标页面返回错误（如 403/404）。链接可能已失效，建议核对后再访问。",
  },
  cert_invalid: {
    label: "证书异常",
    color: "orange",
    tip: "原站 HTTPS 证书校验失败，浏览器访问时可能弹出安全警告。",
  },
  unreachable: {
    label: "暂无法访问",
    color: "red",
    tip: "最近一次巡检时原站连接超时或被拒绝，可能为临时故障。",
  },
  moved: {
    label: "站点已迁移",
    color: "volcano",
    tip: "原站已重定向到其他域名，原链接可能已迁移。",
  },
};

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
  // Only offer the "搜索" button when we have a registered direct-search template
  // for this source. The previous Google site: fallback produced empty results
  // for download mirrors and un-indexed sites (e.g. archive.cbetaonline.cn),
  // misleading users. If a source lacks a template, the button is hidden.
  const searchUrl = searchQuery ? buildSearchUrl(s.code, searchQuery) : null;

  const health =
    s.health_status && s.health_status !== "ok" ? HEALTH_BADGE[s.health_status] : null;
  const healthCheckedAt = s.health_checked_at
    ? new Date(s.health_checked_at).toLocaleDateString("zh-CN")
    : null;
  // For a moved source, health_detail is the redirect target — the one piece
  // of actionable context worth surfacing in the badge tooltip.
  const healthTooltip = health
    ? [
        health.tip,
        s.health_status === "moved" && s.health_detail
          ? `现重定向至：${s.health_detail}`
          : null,
        healthCheckedAt ? `最近巡检：${healthCheckedAt}` : null,
      ]
        .filter(Boolean)
        .join("\n")
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
          {health && (
            <Tooltip title={<span style={{ whiteSpace: "pre-line" }}>{healthTooltip}</span>}>
              <Tag color={health.color} className="source-card-badge">
                <WarningOutlined /> {health.label}
              </Tag>
            </Tooltip>
          )}
          {s.has_local_fulltext && (
            <Tooltip title="正文已入库 FoJin 数据库，可在站内直接阅读、引用与全文检索">
              <Tag color="green" className="source-card-badge">
                <ReadOutlined /> 已入库
              </Tag>
            </Tooltip>
          )}
          {s.has_remote_fulltext && !s.has_local_fulltext && (
            <Tooltip title="全文托管在原站，跳转后可阅读，本站仅做导航与去重">
              <Tag color="cyan" className="source-card-badge">
                <ReadOutlined /> 外站全文
              </Tag>
            </Tooltip>
          )}
          {s.supports_search && (
            <Tooltip title="原站提供搜索功能；若已注册 URL 模板，下方会出现「搜索」直达按钮">
              <Tag color="blue" className="source-card-badge">
                <SearchOutlined /> 可搜索
              </Tag>
            </Tooltip>
          )}
          {s.supports_iiif && (
            <Tooltip title="提供 IIIF 或高清扫描影像（写本、刻本、绘画等）">
              <Tag color="purple" className="source-card-badge">
                <FileImageOutlined /> 影像
              </Tag>
            </Tooltip>
          )}
          {s.supports_api && (
            <Tooltip title="提供机读 API（REST / RDF / IIIF 等），可程序化调用">
              <Tag color="orange" className="source-card-badge">
                <ApiOutlined /> API
              </Tag>
            </Tooltip>
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
