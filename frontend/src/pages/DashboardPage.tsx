import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import { Switch, Spin, Empty } from "antd";
import { useTranslation } from "react-i18next";
import { getStatsOverview } from "../api/stats";
import { useTimelineStore } from "../stores/timelineStore";
import SummaryCards from "../components/dashboard/SummaryCards";
import DynastyBarChart from "../components/dashboard/DynastyBarChart";
import LanguageDonut from "../components/dashboard/LanguageDonut";
import CategoryTreemap from "../components/dashboard/CategoryTreemap";
import SourceCoverageChart from "../components/dashboard/SourceCoverageChart";
import TranslationTrendChart from "../components/dashboard/TranslationTrendChart";
import TopTranslatorsChart from "../components/dashboard/TopTranslatorsChart";
import "../styles/dashboard.css";

export default function DashboardPage() {
  const { t } = useTranslation();
  const { scholarlyMode, toggleScholarlyMode } = useTimelineStore();

  const { data, isLoading } = useQuery({
    queryKey: ["statsOverview"],
    queryFn: getStatsOverview,
    staleTime: 3600000,
  });

  if (isLoading) {
    return (
      <div className="dashboard-container" style={{ textAlign: "center", paddingTop: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="dashboard-container" style={{ textAlign: "center", paddingTop: 80 }}>
        <Empty description={t("common.noData")} />
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      <Helmet>
        <title>{t("dashboard.title")}</title>
      </Helmet>

      <div className="dashboard-header">
        <h2 style={{ fontFamily: '"Noto Serif SC", serif', margin: 0 }}>
          {t("dashboard.title")}
        </h2>
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span>{t("dashboard.scholarlyMode")}</span>
          <Switch checked={scholarlyMode} onChange={toggleScholarlyMode} />
        </label>
      </div>

      <div className="dashboard-grid">
        {/* Row 1: SummaryCards (full-width) */}
        <SummaryCards summary={data.summary} scholarlyMode={scholarlyMode} />

        {/* Row 2: DynastyBarChart | LanguageDonut */}
        <DynastyBarChart data={data.dynasty_distribution} scholarlyMode={scholarlyMode} />
        <div className="dashboard-card">
          <h3>{t("dashboard.languageDistribution")}</h3>
          <LanguageDonut data={data.language_distribution} scholarlyMode={scholarlyMode} />
        </div>

        {/* Row 3: CategoryTreemap | SourceCoverageChart */}
        <div className="dashboard-card">
          <h3>{t("dashboard.categoryBreakdown")}</h3>
          <CategoryTreemap data={data.category_distribution} scholarlyMode={scholarlyMode} />
        </div>
        <div className="dashboard-card">
          <h3>{t("dashboard.sourceCoverage")}</h3>
          <SourceCoverageChart data={data.source_coverage} scholarlyMode={scholarlyMode} />
        </div>

        {/* Row 4: TranslationTrendChart | TopTranslatorsChart */}
        <div className="dashboard-card">
          <h3>{t("dashboard.translationTrend")}</h3>
          <TranslationTrendChart data={data.dynasty_distribution} scholarlyMode={scholarlyMode} />
        </div>
        <div className="dashboard-card">
          <h3>{t("dashboard.topTranslators")}</h3>
          <TopTranslatorsChart data={data.top_translators} scholarlyMode={scholarlyMode} />
        </div>
      </div>
    </div>
  );
}
