import { useTranslation } from "react-i18next";
import type { StatsSummary } from "../../api/stats";

interface SummaryCardsProps {
  summary: StatsSummary;
  scholarlyMode: boolean;
}

export default function SummaryCards({ summary, scholarlyMode }: SummaryCardsProps) {
  const { t } = useTranslation();

  const cards = [
    { key: "totalTexts", value: summary.total_texts },
    { key: "totalSources", value: summary.total_sources },
    { key: "totalLanguages", value: summary.total_languages },
    { key: "totalEntities", value: summary.total_kg_entities },
    { key: "totalRelations", value: summary.total_kg_relations },
    { key: "totalDictEntries", value: summary.total_dict_entries },
  ];

  return (
    <div className="dashboard-card full-width">
      <h3>{t("dashboard.platformSummary")}</h3>
      <div className="summary-cards">
        {cards.map((card) => (
          <div key={card.key} className="summary-card">
            <div className="value">{card.value.toLocaleString()}</div>
            <div className="label">{t(`dashboard.${card.key}`)}</div>
            {scholarlyMode && (
              <div className="scholarly-label">{card.key}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
