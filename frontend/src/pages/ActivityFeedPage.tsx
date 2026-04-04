import { useState } from "react";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import { Tabs, Spin, Empty, Tag, Pagination, Select, Slider } from "antd";
import { useTranslation } from "react-i18next";
import {
  getFeedSummary,
  getSourceUpdates,
  getAcademicFeeds,
} from "../api/feed";
import type { SourceUpdateItem, AcademicFeedItem } from "../api/feed";
import "../styles/activity-feed.css";

function relativeTime(dateStr: string, t: (key: string) => string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return t("activity.justNow");
  if (diffMin < 60) return t("activity.minutesAgo").replace("{{n}}", String(diffMin));
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return t("activity.hoursAgo").replace("{{n}}", String(diffHr));
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return t("activity.daysAgo").replace("{{n}}", String(diffDay));
  const diffMonth = Math.floor(diffDay / 30);
  return t("activity.monthsAgo").replace("{{n}}", String(diffMonth));
}

function dotClass(updateType: string): string {
  if (["new_text", "translation", "scan", "schema"].includes(updateType)) {
    return `feed-item-dot ${updateType}`;
  }
  return "feed-item-dot default";
}

function badgeClass(updateType: string): string {
  if (["new_text", "translation", "scan", "schema"].includes(updateType)) {
    return `update-type-badge ${updateType}`;
  }
  return "update-type-badge";
}

function SourceUpdateRow({ item, t }: { item: SourceUpdateItem; t: (key: string) => string }) {
  return (
    <div className="feed-item">
      <span className={dotClass(item.update_type)} />
      <div className="feed-item-content">
        <div className="feed-item-title">
          {item.source_name_zh}
          <Tag style={{ marginLeft: 8 }}>{item.count}</Tag>
        </div>
        <div className="feed-item-summary">{item.summary}</div>
        <div className="feed-item-meta">
          <span className={badgeClass(item.update_type)}>
            {t(`activity.updateType.${item.update_type}`) || item.update_type}
          </span>
          <span>{relativeTime(item.detected_at, t)}</span>
        </div>
      </div>
    </div>
  );
}

function AcademicRow({ item }: { item: AcademicFeedItem }) {
  const dateStr = item.published_at
    ? new Date(item.published_at).toLocaleDateString()
    : "";
  return (
    <div className="feed-item">
      <div className="feed-item-content">
        <div className="feed-item-title">
          <a href={item.url} target="_blank" rel="noopener noreferrer">
            {item.title}
          </a>
        </div>
        {item.summary && <div className="feed-item-summary">{item.summary}</div>}
        <div className="feed-item-meta">
          <Tag color="blue">{item.feed_source}</Tag>
          {item.category && <Tag>{item.category}</Tag>}
          {item.author && <span>{item.author}</span>}
          {dateStr && <span>{dateStr}</span>}
        </div>
      </div>
    </div>
  );
}

/* ---------- Tab 1: Overview ---------- */
function OverviewTab() {
  const { t } = useTranslation();
  const { data, isLoading } = useQuery({
    queryKey: ["feedSummary"],
    queryFn: getFeedSummary,
    staleTime: 300000,
  });

  if (isLoading) return <div style={{ textAlign: "center", padding: 40 }}><Spin size="large" /></div>;
  if (!data) return <Empty description={t("activity.noData")} />;

  return (
    <>
      <div className="feed-stat-cards">
        <div className="feed-stat-card">
          <div className="value">{data.stats.source_updates_30d}</div>
          <div className="label">{t("activity.sourceUpdates30d")}</div>
        </div>
        <div className="feed-stat-card">
          <div className="value">{data.stats.academic_feeds_30d}</div>
          <div className="label">{t("activity.academicFeeds30d")}</div>
        </div>
        <div className="feed-stat-card">
          <div className="value">{data.stats.active_sources}</div>
          <div className="label">{t("activity.activeSources")}</div>
        </div>
      </div>

      <div className="feed-card">
        <h3>{t("activity.recentSourceUpdates")}</h3>
        <div className="feed-list">
          {data.recent_source_updates.length === 0 ? (
            <Empty description={t("activity.noData")} />
          ) : (
            data.recent_source_updates.map((item) => (
              <SourceUpdateRow key={item.id} item={item} t={t} />
            ))
          )}
        </div>
      </div>

      <div className="feed-card">
        <h3>{t("activity.recentAcademic")}</h3>
        <div className="feed-list">
          {data.recent_academic.length === 0 ? (
            <Empty description={t("activity.noData")} />
          ) : (
            data.recent_academic.map((item) => (
              <AcademicRow key={item.id} item={item} />
            ))
          )}
        </div>
      </div>
    </>
  );
}

/* ---------- Tab 2: Source Updates ---------- */
function SourceUpdatesTab() {
  const { t } = useTranslation();
  const [sourceId, setSourceId] = useState<number | undefined>();
  const [updateType, setUpdateType] = useState<string | undefined>();
  const [days, setDays] = useState(30);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["sourceUpdates", { sourceId, updateType, days, page }],
    queryFn: () =>
      getSourceUpdates({
        source_id: sourceId,
        update_type: updateType,
        days,
        page,
        page_size: pageSize,
      }),
    staleTime: 120000,
  });

  return (
    <>
      <div className="feed-filter-bar">
        <span className="filter-label">{t("activity.filterSource")}:</span>
        <Select
          allowClear
          placeholder={t("activity.allSources")}
          style={{ width: 180 }}
          value={sourceId}
          onChange={(v) => { setSourceId(v); setPage(1); }}
        />
        <span className="filter-label">{t("activity.filterType")}:</span>
        <Select
          allowClear
          placeholder={t("activity.allTypes")}
          style={{ width: 160 }}
          value={updateType}
          onChange={(v) => { setUpdateType(v); setPage(1); }}
          options={[
            { value: "new_text", label: t("activity.updateType.new_text") },
            { value: "translation", label: t("activity.updateType.translation") },
            { value: "scan", label: t("activity.updateType.scan") },
            { value: "schema", label: t("activity.updateType.schema") },
          ]}
        />
        <span className="filter-label">{t("activity.filterDays")}:</span>
        <Slider
          min={7}
          max={90}
          value={days}
          onChange={(v) => { setDays(v); setPage(1); }}
          style={{ width: 120 }}
          tooltip={{ formatter: (v) => `${v} ${t("activity.days")}` }}
        />
      </div>

      {isLoading ? (
        <div style={{ textAlign: "center", padding: 40 }}><Spin size="large" /></div>
      ) : !data || data.items.length === 0 ? (
        <Empty description={t("activity.noData")} />
      ) : (
        <>
          <div className="feed-card">
            <div className="feed-list">
              {data.items.map((item) => (
                <SourceUpdateRow key={item.id} item={item} t={t} />
              ))}
            </div>
          </div>
          <div className="feed-pagination">
            <Pagination
              current={page}
              pageSize={pageSize}
              total={data.total}
              onChange={setPage}
              showSizeChanger={false}
            />
          </div>
        </>
      )}
    </>
  );
}

/* ---------- Tab 3: Academic ---------- */
function AcademicTab() {
  const { t } = useTranslation();
  const [feedSource, setFeedSource] = useState<string | undefined>();
  const [category, setCategory] = useState<string | undefined>();
  const [days, setDays] = useState(90);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["academicFeeds", { feedSource, category, days, page }],
    queryFn: () =>
      getAcademicFeeds({
        feed_source: feedSource,
        category,
        days,
        page,
        page_size: pageSize,
      }),
    staleTime: 120000,
  });

  return (
    <>
      <div className="feed-filter-bar">
        <span className="filter-label">{t("activity.filterFeedSource")}:</span>
        <Select
          allowClear
          placeholder={t("activity.allSources")}
          style={{ width: 180 }}
          value={feedSource}
          onChange={(v) => { setFeedSource(v); setPage(1); }}
          options={[
            { value: "cbeta", label: "CBETA" },
            { value: "84000_blog", label: "84000" },
            { value: "bdrc_news", label: "BDRC" },
            { value: "bdk_america", label: "BDK America" },
            { value: "buddhistdoor", label: "Buddhistdoor" },
            { value: "lions_roar", label: "Lion's Roar" },
            { value: "tricycle", label: "Tricycle" },
            { value: "accesstoinsight", label: "Access to Insight" },
            { value: "iabs", label: "IABS" },
          ]}
        />
        <span className="filter-label">{t("activity.filterCategory")}:</span>
        <Select
          allowClear
          placeholder={t("activity.allCategories")}
          style={{ width: 160 }}
          value={category}
          onChange={(v) => { setCategory(v); setPage(1); }}
          options={[
            { value: "paper", label: t("activity.categoryPaper") },
            { value: "translation", label: t("activity.categoryTranslation") },
            { value: "news", label: t("activity.categoryNews") },
            { value: "digitization", label: t("activity.categoryDigitization") },
            { value: "conference", label: t("activity.categoryConference") },
          ]}
        />
        <span className="filter-label">{t("activity.filterDays")}:</span>
        <Slider
          min={7}
          max={180}
          value={days}
          onChange={(v) => { setDays(v); setPage(1); }}
          style={{ width: 120 }}
          tooltip={{ formatter: (v) => `${v} ${t("activity.days")}` }}
        />
      </div>

      {isLoading ? (
        <div style={{ textAlign: "center", padding: 40 }}><Spin size="large" /></div>
      ) : !data || data.items.length === 0 ? (
        <Empty description={t("activity.noData")} />
      ) : (
        <>
          <div className="feed-card">
            <div className="feed-list">
              {data.items.map((item) => (
                <AcademicRow key={item.id} item={item} />
              ))}
            </div>
          </div>
          <div className="feed-pagination">
            <Pagination
              current={page}
              pageSize={pageSize}
              total={data.total}
              onChange={setPage}
              showSizeChanger={false}
            />
          </div>
        </>
      )}
    </>
  );
}

/* ---------- Main Page ---------- */
export default function ActivityFeedPage() {
  const { t } = useTranslation();

  const tabItems = [
    { key: "overview", label: t("activity.overview"), children: <OverviewTab /> },
    { key: "source-updates", label: t("activity.sourceUpdates"), children: <SourceUpdatesTab /> },
    { key: "academic", label: t("activity.academic"), children: <AcademicTab /> },
  ];

  return (
    <div className="activity-feed-container">
      <Helmet>
        <title>{t("activity.title")}</title>
      </Helmet>

      <div className="activity-feed-header">
        <h2>{t("activity.title")}</h2>
      </div>

      <Tabs defaultActiveKey="overview" items={tabItems} />
    </div>
  );
}
