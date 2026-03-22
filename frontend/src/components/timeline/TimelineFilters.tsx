import { useTranslation } from "react-i18next";
import { Checkbox, Button, Select } from "antd";
import { useTimelineStore } from "../../stores/timelineStore";

const CATEGORY_OPTIONS = [
  { label: "经 Sūtra", value: "sutra" },
  { label: "律 Vinaya", value: "vinaya" },
  { label: "论 Abhidharma", value: "abhidharma" },
  { label: "疏 Commentary", value: "commentary" },
];

const LANGUAGE_OPTIONS = [
  { value: "lzh", label: "漢文" },
  { value: "sa", label: "梵文" },
  { value: "pi", label: "巴利文" },
  { value: "bo", label: "藏文" },
  { value: "en", label: "English" },
];

export default function TimelineFilters() {
  const { t } = useTranslation();
  const { filters, setFilter, resetFilters } = useTimelineStore();

  return (
    <div className="timeline-filters">
      <h4>{t("timeline.filterCategory", "分类")}</h4>
      <Checkbox.Group
        options={CATEGORY_OPTIONS}
        value={filters.category ? filters.category.split(",") : []}
        onChange={(vals) => {
          setFilter("category", vals.length > 0 ? vals.join(",") : null);
        }}
        style={{ display: "flex", flexDirection: "column", gap: 6 }}
      />

      <h4 style={{ marginTop: 16 }}>{t("timeline.filterLanguage", "语言")}</h4>
      <Select
        options={LANGUAGE_OPTIONS}
        value={filters.language || undefined}
        onChange={(val) => setFilter("language", val || null)}
        placeholder={t("timeline.selectLanguage", "选择语言")}
        allowClear
        style={{ width: "100%" }}
      />

      <div style={{ marginTop: 16 }}>
        <Button size="small" onClick={resetFilters}>
          {t("common.reset", "重置")}
        </Button>
      </div>
    </div>
  );
}
