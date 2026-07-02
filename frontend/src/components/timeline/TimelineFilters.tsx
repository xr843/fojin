import { useTranslation } from "react-i18next";
import { Checkbox, Button, Select } from "antd";
import { useTimelineStore } from "../../stores/timelineStore";

const CATEGORY_OPTIONS = [
  { labelKey: "timeline.category.sutra", value: "sutra" },
  { labelKey: "timeline.category.vinaya", value: "vinaya" },
  { labelKey: "timeline.category.abhidharma", value: "abhidharma" },
  { labelKey: "timeline.category.commentary", value: "commentary" },
];

const LANGUAGE_OPTIONS = [
  { value: "lzh", labelKey: "lang.lzh" },
  { value: "sa", labelKey: "lang.sa" },
  { value: "pi", labelKey: "lang.pi" },
  { value: "bo", labelKey: "lang.bo" },
  { value: "en", labelKey: "lang.en" },
];

export default function TimelineFilters() {
  const { t } = useTranslation();
  const { filters, setFilter, resetFilters } = useTimelineStore();

  return (
    <div className="timeline-filters">
      <h4>{t("timeline.filterCategory")}</h4>
      <Checkbox.Group
        options={CATEGORY_OPTIONS.map((option) => ({
          value: option.value,
          label: t(option.labelKey),
        }))}
        value={filters.category ? filters.category.split(",") : []}
        onChange={(vals) => {
          setFilter("category", vals.length > 0 ? vals.join(",") : null);
        }}
        style={{ display: "flex", flexDirection: "column", gap: 6 }}
      />

      <h4 style={{ marginTop: 16 }}>{t("timeline.filterLanguage")}</h4>
      <Select
        options={LANGUAGE_OPTIONS.map((option) => ({
          value: option.value,
          label: t(option.labelKey),
        }))}
        value={filters.language || undefined}
        onChange={(val) => setFilter("language", val || null)}
        placeholder={t("timeline.selectLanguage")}
        allowClear
        style={{ width: "100%" }}
      />

      <div style={{ marginTop: 16 }}>
        <Button size="small" onClick={resetFilters}>
          {t("timeline.resetFilters")}
        </Button>
      </div>
    </div>
  );
}
