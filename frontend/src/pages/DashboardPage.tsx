import { useState } from "react";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import { Switch, Spin, Empty } from "antd";
import { useTranslation } from "react-i18next";
import { getStatsOverview } from "../api/stats";
import SummaryCards from "../components/dashboard/SummaryCards";
import DynastyBarChart from "../components/dashboard/DynastyBarChart";
import "../styles/dashboard.css";

export default function DashboardPage() {
  const { t } = useTranslation();
  const [scholarlyMode, setScholarlyMode] = useState(false);

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
          <Switch checked={scholarlyMode} onChange={setScholarlyMode} />
        </label>
      </div>

      <div className="dashboard-grid">
        <SummaryCards summary={data.summary} scholarlyMode={scholarlyMode} />
        <DynastyBarChart data={data.dynasty_distribution} scholarlyMode={scholarlyMode} />
      </div>
    </div>
  );
}
