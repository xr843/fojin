import { Tag, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
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
import { localizedSourceName, alternateSourceName } from "../../utils/sourceName";
import { buildSearchUrl, getLangName, localizedLangName } from "../../utils/sourceUrls";
import { LANG_ORDER, getChannelLabel, trackSourceClick } from "./constants";

interface SourceCardProps {
  source: DataSource;
  searchQuery: string;
}

// Cron-updated reachability verdicts worth surfacing to readers. "ok" shows
// nothing — only problems get a badge, to keep healthy cards uncluttered.
const HEALTH_BADGE: Record<
  Exclude<DataSource["health_status"], "ok">,
  { labelKey: string; color: string; tipKey: string }
> = {
  degraded: {
    labelKey: "sources.health_degraded",
    color: "gold",
    tipKey: "sources.health_degraded_tip",
  },
  cert_invalid: {
    labelKey: "sources.health_cert_invalid",
    color: "orange",
    tipKey: "sources.health_cert_invalid_tip",
  },
  unreachable: {
    labelKey: "sources.health_unreachable",
    color: "default",
    tipKey: "sources.health_unreachable_tip",
  },
  moved: {
    labelKey: "sources.health_moved",
    color: "volcano",
    tipKey: "sources.health_moved_tip",
  },
};

export default function SourceCard({ source: s, searchQuery }: SourceCardProps) {
  const { t } = useTranslation();
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
  // for download mirrors and un-indexed sites (e.g. cbeta.org/ebooks),
  // misleading users. If a source lacks a template, the button is hidden.
  const searchUrl = searchQuery ? buildSearchUrl(s.code, searchQuery) : null;

  // Badge only on verdicts that hold outside the prober's own vantage. The cron
  // runs from a single VPS: a timeout there, a DNS miss, or a CDN edge handing
  // back its own default certificate are facts about the probe, not the site —
  // 0172 added health_confidence for exactly this and the badge was never wired
  // to it, so every low-confidence verdict has been telling readers that live
  // institutions (Bodleian, Princeton, CNKI …) are broken.
  const health =
    s.health_status && s.health_status !== "ok" && s.health_confidence === "high"
      ? HEALTH_BADGE[s.health_status]
      : null;
  const healthCheckedAt = s.health_checked_at
    ? new Date(s.health_checked_at).toLocaleDateString("zh-CN")
    : null;
  // health_detail carries per-source context the generic tip lacks: for a moved
  // source it's the redirect target, for degraded/unreachable/cert_invalid it's
  // the probe's specific failure reason. Surface it for every problem state.
  const healthDetailLine =
    health && s.health_detail
      ? s.health_status === "moved"
        ? t("sources.health_redirect", { detail: s.health_detail })
        : t("sources.health_detail", { detail: s.health_detail })
      : null;
  const healthTooltip = health
    ? [
        t(health.tipKey),
        healthDetailLine,
        healthCheckedAt ? t("sources.health_last_checked", { date: healthCheckedAt }) : null,
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
          <span className="source-card-name">{localizedSourceName(s)}</span>
          {alternateSourceName(s) && (
            <span className="source-card-name-en">{alternateSourceName(s)}</span>
          )}
        </div>
        <div className="source-card-badges">
          {health && (
            <Tooltip title={<span style={{ whiteSpace: "pre-line" }}>{healthTooltip}</span>}>
              <Tag color={health.color} className="source-card-badge">
                <WarningOutlined /> {t(health.labelKey)}
              </Tag>
            </Tooltip>
          )}
          {s.has_local_fulltext && (
            <Tooltip title={t("sources.cap_local_tip")}>
              <Tag color="green" className="source-card-badge">
                <ReadOutlined /> {t("sources.badge_local")}
              </Tag>
            </Tooltip>
          )}
          {s.has_remote_fulltext && !s.has_local_fulltext && (
            <Tooltip title={t("sources.cap_remote_tip")}>
              <Tag color="cyan" className="source-card-badge">
                <ReadOutlined /> {t("sources.cap_remote")}
              </Tag>
            </Tooltip>
          )}
          {s.supports_search && (
            <Tooltip title={t("sources.badge_searchable_tip")}>
              <Tag color="blue" className="source-card-badge">
                <SearchOutlined /> {t("sources.badge_searchable")}
              </Tag>
            </Tooltip>
          )}
          {s.supports_iiif && (
            <Tooltip title={t("sources.badge_iiif_tip")}>
              <Tag color="purple" className="source-card-badge">
                <FileImageOutlined /> {t("sources.cap_iiif")}
              </Tag>
            </Tooltip>
          )}
          {s.supports_api && (
            <Tooltip title={t("sources.cap_api_tip")}>
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
          <div className="source-card-dists-title">{t("sources.distributions_title")}</div>
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
                  {getChannelLabel(d.channel_type, t)}
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
            {localizedLangName(l, t)}
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
            <GlobalOutlined /> {t("sources.visit_site")}
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
            <LinkOutlined /> {t("sources.search_query_button", { query: searchQuery })}
          </a>
        )}
      </div>
    </div>
  );
}
