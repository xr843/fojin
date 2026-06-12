import { Button } from "antd";
import { CloseOutlined, EnvironmentOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { KGGeoEntity } from "../../api/client";

interface MapEntityPopupProps {
  entity: KGGeoEntity;
  onClose: () => void;
}

const TYPE_LABEL_KEYS: Record<string, string> = {
  person: "geo.type_person",
  text: "geo.type_text",
  monastery: "geo.type_temple",
  school: "geo.type_school",
  place: "geo.type_place",
  concept: "geo.type_concept",
  dynasty: "geo.type_dynasty",
};

function formatYear(t: TFunction, year: number): string {
  if (year < 0) return t("geo.year_bce", { n: Math.abs(year) });
  return t("geo.year_ce", { n: year });
}

function formatYearRange(t: TFunction, start: number | null, end: number | null): string {
  if (start !== null && end !== null) return `${formatYear(t, start)} — ${formatYear(t, end)}`;
  if (start !== null) return `${formatYear(t, start)} —`;
  if (end !== null) return `— ${formatYear(t, end)}`;
  return "";
}

export default function MapEntityPopup({
  entity,
  onClose,
}: MapEntityPopupProps) {
  const { t } = useTranslation();
  const yearText = formatYearRange(t, entity.year_start, entity.year_end);
  const address = [entity.province, entity.city, entity.district].filter(Boolean).join("");

  return (
    <div className="kg-map-popup-container">
      <div className="kg-map-popup">
        <div className="kg-map-popup-header">
          <span className={`kg-type-tag kg-type-tag--${entity.entity_type}`}>
            {TYPE_LABEL_KEYS[entity.entity_type] ? t(TYPE_LABEL_KEYS[entity.entity_type]) : entity.entity_type}
          </span>
          <Button
            type="text"
            size="small"
            icon={<CloseOutlined />}
            onClick={onClose}
          />
        </div>

        <div style={{ padding: "8px 0 0" }}>
          <div className="kg-map-popup-name">{entity.name_zh}</div>
          {entity.name_en && (
            <div className="kg-map-popup-en">{entity.name_en}</div>
          )}
        </div>

        {address && (
          <div style={{ fontSize: 12, color: "#999", padding: "4px 14px 0", display: "flex", alignItems: "center", gap: 4 }}>
            <EnvironmentOutlined style={{ fontSize: 11 }} />
            {address}
          </div>
        )}

        {entity.description && (
          <div className="kg-map-popup-desc">{entity.description}</div>
        )}

        {yearText && (
          <div className="kg-map-popup-year">{yearText}</div>
        )}
      </div>
    </div>
  );
}
