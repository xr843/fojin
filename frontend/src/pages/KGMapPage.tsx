import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Checkbox, Spin, Empty, Tooltip, Switch } from "antd";
import { GlobalOutlined, BarChartOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import DeckGLMap from "../components/kg-map/DeckGLMap";
import MapEntityPopup from "../components/kg-map/MapEntityPopup";
import { getKGGeoEntities, getKGLineageArcs } from "../api/client";
import type { KGGeoEntity } from "../api/client";
import "../styles/kg-map.css";

const ENTITY_TYPE_OPTIONS = [
  { value: "monastery", label: "寺院" },
  { value: "place", label: "地点" },
  { value: "person", label: "人物" },
  { value: "school", label: "宗派" },
];

const TYPE_CSS_COLORS: Record<string, string> = {
  person: "#dc2626",
  monastery: "#22c55e",
  place: "#7c3aed",
  school: "#ea580c",
};

export default function KGMapPage() {
  const navigate = useNavigate();

  const [entityTypes, setEntityTypes] = useState<string[]>([
    "monastery",
    "place",
    "person",
  ]);
  const [showArcs, setShowArcs] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<KGGeoEntity | null>(null);
  const [chineseOnly, setChineseOnly] = useState(false);

  /* ---------- Queries ---------- */

  const { data: geoData, isLoading: geoLoading } = useQuery({
    queryKey: ["kg-geo"],
    queryFn: () => getKGGeoEntities({ limit: 50000 }),
    staleTime: 5 * 60_000,
  });

  const { data: arcData } = useQuery({
    queryKey: ["kg-lineage-arcs"],
    queryFn: () => getKGLineageArcs({ limit: 8000 }),
    staleTime: 5 * 60_000,
    enabled: showArcs,
  });

  /* ---------- Derived ---------- */

  const filteredEntities = useMemo(() => {
    const CJK_REGEX = /[\u4E00-\u9FFF\u3040-\u30FF]/;
    const HANGUL_REGEX = /[\uAC00-\uD7AF]/;
    const isChineseName = (name: string | null | undefined): boolean => {
      if (!name) return false;
      if (HANGUL_REGEX.test(name)) return false;
      return CJK_REGEX.test(name);
    };
    if (!chineseOnly) return geoData?.entities ?? [];
    return (geoData?.entities ?? []).filter((e) => isChineseName(e.name_zh));
  }, [geoData, chineseOnly]);

  /* ---------- Handlers ---------- */

  const handleEntityClick = (entity: KGGeoEntity) => {
    setSelectedEntity(entity);
  };

  const handleViewInGraph = (entityId: number) => {
    navigate(`/kg?entity=${entityId}`);
  };

  /* ---------- Render ---------- */

  return (
    <div className="kg-map-page">
      {/* Header */}
      <div className="kg-map-header">
        <GlobalOutlined />
        <h3>佛教地理</h3>
        {geoData && (
          <Tooltip title={chineseOnly ? "中文名实体" : "所有实体"}>
            <span className="kg-map-stats">
              <BarChartOutlined />
              <span>
                {filteredEntities.length.toLocaleString()} 个地点
                {chineseOnly && <span className="kg-map-stats-filter"> · 纯中文</span>}
              </span>
            </span>
          </Tooltip>
        )}
      </div>

      {/* Toolbar */}
      <div className="kg-map-toolbar">
        <div className="kg-map-toolbar-row">
          <span className="kg-map-filter-label">实体类型:</span>
          <Checkbox.Group
            value={entityTypes}
            onChange={(vals) => setEntityTypes(vals as string[])}
            options={ENTITY_TYPE_OPTIONS}
          />
          <Checkbox
            checked={showArcs}
            onChange={(e) => setShowArcs(e.target.checked)}
          >
            师承传线
          </Checkbox>
          <span className="kg-map-filter-label">纯中文:</span>
          <Switch
            size="small"
            checked={chineseOnly}
            onChange={setChineseOnly}
          />
        </div>
      </div>

      {/* Map Container */}
      <div className="kg-map-container">
        {geoLoading ? (
          <div className="kg-map-loading">
            <Spin size="large" />
          </div>
        ) : !geoData?.entities.length ? (
          <div className="kg-map-loading">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无地理数据"
            />
          </div>
        ) : (
          <>
            <DeckGLMap
              geoEntities={filteredEntities}
              lineageArcs={arcData?.arcs ?? []}
              showArcs={showArcs}
              currentYear={null}
              entityTypeFilter={entityTypes}
              onEntityClick={handleEntityClick}
            />

            <div className="kg-map-legend">
              {ENTITY_TYPE_OPTIONS.filter((t) => entityTypes.includes(t.value)).map((t) => (
                <span key={t.value} className="kg-map-legend-item">
                  <span className="kg-legend-dot" style={{ background: TYPE_CSS_COLORS[t.value] || "#888" }} />
                  {t.label}
                </span>
              ))}
              {showArcs && (
                <span className="kg-map-legend-item">
                  <span className="kg-legend-line" style={{ background: "#c08b3e" }} />
                  师承
                </span>
              )}
            </div>

            {/* Time filter hidden: only 0.7% of entities have year data (see issue tracker) */}

            {selectedEntity && (
              <MapEntityPopup
                entity={selectedEntity}
                onClose={() => setSelectedEntity(null)}
                onViewInGraph={handleViewInGraph}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
