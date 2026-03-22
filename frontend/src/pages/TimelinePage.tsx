import { useTranslation } from "react-i18next";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import { Tabs, Switch, Spin, Empty, Pagination } from "antd";
import { useState } from "react";
import { getStatsTimeline } from "../api/stats";
import { useTimelineStore } from "../stores/timelineStore";
import TimelineChart from "../components/timeline/TimelineChart";
import TimelineFilters from "../components/timeline/TimelineFilters";
import "../styles/timeline.css";

export default function TimelinePage() {
  const { t } = useTranslation();
  const {
    dimension,
    setDimension,
    scholarlyMode,
    toggleScholarlyMode,
    filters,
  } = useTimelineStore();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["statsTimeline", dimension, filters, page],
    queryFn: () =>
      getStatsTimeline({
        dimension,
        category: filters.category ?? undefined,
        language: filters.language ?? undefined,
        source_id: filters.sourceId ?? undefined,
        page,
        page_size: 200,
      }),
    staleTime: 3600000,
  });

  return (
    <>
      <Helmet>
        <title>{t("timeline.title", "时间线")} - FoJin</title>
      </Helmet>
      <div className="timeline-container">
        <div className="timeline-header">
          <h2
            style={{
              fontFamily: '"Noto Serif SC", serif',
              color: "var(--fj-ink)",
            }}
          >
            {t("timeline.title", "时间线")}
          </h2>
          <Tabs
            activeKey={dimension}
            onChange={(k) => {
              setDimension(k as typeof dimension);
              setPage(1);
            }}
            items={[
              { key: "texts", label: t("timeline.texts", "典籍") },
              { key: "figures", label: t("timeline.figures", "人物") },
              { key: "schools", label: t("timeline.schools", "宗派") },
            ]}
          />
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>{t("dashboard.scholarlyMode", "学术模式")}</span>
            <Switch checked={scholarlyMode} onChange={toggleScholarlyMode} />
          </label>
        </div>
        <div className="timeline-body">
          <TimelineFilters />
          <div className="timeline-main">
            {isLoading ? (
              <div style={{ textAlign: "center", padding: 80 }}>
                <Spin size="large" />
              </div>
            ) : !data || data.items.length === 0 ? (
              <Empty description={t("common.noData", "暂无数据")} />
            ) : (
              <>
                <TimelineChart
                  items={data.items}
                  scholarlyMode={scholarlyMode}
                />
                {data.total > 200 && (
                  <Pagination
                    current={page}
                    total={data.total}
                    pageSize={200}
                    onChange={setPage}
                    showSizeChanger={false}
                    style={{ marginTop: 16, textAlign: "center" }}
                  />
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
