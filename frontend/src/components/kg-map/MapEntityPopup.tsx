import { Button } from "antd";
import { CloseOutlined, ApartmentOutlined, BookOutlined } from "@ant-design/icons";
import type { KGGeoEntity } from "../../api/client";

interface MapEntityPopupProps {
  entity: KGGeoEntity;
  onClose: () => void;
  onViewInGraph: (entityId: number) => void;
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
  onViewInGraph,
}: MapEntityPopupProps) {
  const yearText = formatYearRange(entity.year_start, entity.year_end);

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

        {entity.description && (
          <div className="kg-map-popup-desc">{entity.description}</div>
        )}

        {yearText && (
          <div className="kg-map-popup-year">{yearText}</div>
        )}

        <div className="kg-map-popup-actions">
          <Button
            size="small"
            icon={<ApartmentOutlined />}
            onClick={() => onViewInGraph(entity.id)}
          >
            知识图谱
          </Button>
          <Button
            size="small"
            icon={<BookOutlined />}
            onClick={() => onViewInGraph(entity.id)}
          >
            详情
          </Button>
        </div>
      </div>
    </div>
  );
}
