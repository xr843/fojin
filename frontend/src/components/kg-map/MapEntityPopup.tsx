import { Button } from "antd";
import { CloseOutlined, EnvironmentOutlined } from "@ant-design/icons";
import type { KGGeoEntity } from "../../api/client";

interface MapEntityPopupProps {
  entity: KGGeoEntity;
  onClose: () => void;
}

const TYPE_LABEL_MAP: Record<string, string> = {
  person: "人物",
  text: "典籍",
  monastery: "寺院",
  school: "宗派",
  place: "地点",
  concept: "概念",
  dynasty: "朝代",
};

function formatYear(year: number): string {
  if (year < 0) return `公元前${Math.abs(year)}年`;
  return `公元${year}年`;
}

function formatYearRange(start: number | null, end: number | null): string {
  if (start !== null && end !== null) return `${formatYear(start)} — ${formatYear(end)}`;
  if (start !== null) return `${formatYear(start)} —`;
  if (end !== null) return `— ${formatYear(end)}`;
  return "";
}

export default function MapEntityPopup({
  entity,
  onClose,
}: MapEntityPopupProps) {
  const yearText = formatYearRange(entity.year_start, entity.year_end);
  const address = [entity.province, entity.city, entity.district].filter(Boolean).join("");

  return (
    <div className="kg-map-popup-container">
      <div className="kg-map-popup">
        <div className="kg-map-popup-header">
          <span className={`kg-type-tag kg-type-tag--${entity.entity_type}`}>
            {TYPE_LABEL_MAP[entity.entity_type] || entity.entity_type}
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
