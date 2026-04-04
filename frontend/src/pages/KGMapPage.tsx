import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Checkbox, Spin, Empty, Tooltip, Radio, Select } from "antd";
import { GlobalOutlined, BarChartOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import DeckGLMap from "../components/kg-map/DeckGLMap";
import MapEntityPopup from "../components/kg-map/MapEntityPopup";
import TimeSlider from "../components/kg-map/TimeSlider";
import LineageGraph from "../components/kg-map/LineageGraph";
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
  person: "#d23c32",
  monastery: "#5aa046",
  place: "#c88c2d",
  school: "#8250be",
};

export default function KGMapPage() {
  const navigate = useNavigate();

  const [entityTypes, setEntityTypes] = useState<string[]>([
    "monastery",
    "place",
    "person",
  ]);
  const [showArcs, setShowArcs] = useState(false);
  const [currentYear, setCurrentYear] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<KGGeoEntity | null>(null);
  const [viewMode, setViewMode] = useState<"map" | "network">("map");
  const [schoolFilter, setSchoolFilter] = useState<string | null>(null);

  // Auto-enable arcs when switching to network mode
  useEffect(() => {
    if (viewMode === "network" && !showArcs) setShowArcs(true);
  }, [viewMode, showArcs]);

  /* ---------- Queries ---------- */

  const { data: geoData, isLoading: geoLoading } = useQuery({
    queryKey: ["kg-geo"],
    queryFn: () => getKGGeoEntities({ limit: 8000 }),
    staleTime: 5 * 60_000,
  });

  const { data: arcData } = useQuery({
    queryKey: ["kg-lineage-arcs"],
    queryFn: () => getKGLineageArcs({ limit: 8000 }),
    staleTime: 5 * 60_000,
    enabled: showArcs,
  });

  /* ---------- Derived ---------- */

  const yearRange = useMemo(() => {
    const entities = geoData?.entities ?? [];
    let min = -500;
    let max = 2000;
    for (const e of entities) {
      if (e.year_start !== null && e.year_start < min) min = e.year_start;
      if (e.year_end !== null && e.year_end > max) max = e.year_end;
    }
    return { min, max };
  }, [geoData]);

  /* ---------- Handlers ---------- */

  const handleEntityClick = (entity: KGGeoEntity) => {
    setSelectedEntity(entity);
  };

  const handleViewInGraph = (entityId: number) => {
    navigate(`/kg?entity=${entityId}`);
  };

  const handlePlayToggle = () => {
    setIsPlaying((p) => !p);
  };

  const handleYearChange = (year: number | null) => {
    setCurrentYear(year);
    if (year === null) setIsPlaying(false);
  };

  /* ---------- Render ---------- */

  return (
    <div className="kg-map-page">
      {/* Header */}
      <div className="kg-map-header">
        <GlobalOutlined />
        <h3>佛教地理</h3>
        {geoData && (
          <Tooltip title="含坐标的实体数量">
            <span className="kg-map-stats">
              <BarChartOutlined />
              <span>{geoData.total.toLocaleString()} 个地点</span>
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
          <Radio.Group
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value)}
            size="small"
            style={{ marginLeft: "auto" }}
          >
            <Radio.Button value="map">地图</Radio.Button>
            <Radio.Button value="network">网络图</Radio.Button>
          </Radio.Group>
          {viewMode === "network" && (
            <Select
              value={schoolFilter}
              onChange={(val) => setSchoolFilter(val)}
              allowClear
              placeholder="宗派筛选"
              size="small"
              style={{ width: 120, marginLeft: 8 }}
              options={[
                { value: "中观", label: "中观" },
                { value: "唯识", label: "唯识" },
                { value: "天台", label: "天台" },
                { value: "华严", label: "华严" },
                { value: "禅宗", label: "禅宗" },
                { value: "净土", label: "净土" },
                { value: "律宗", label: "律宗" },
                { value: "密宗", label: "密宗" },
              ]}
            />
          )}
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
            {viewMode === "map" ? (
              <>
                <DeckGLMap
                  geoEntities={geoData.entities}
                  lineageArcs={arcData?.arcs ?? []}
                  showArcs={showArcs}
                  currentYear={currentYear}
                  entityTypeFilter={entityTypes}
                  onEntityClick={handleEntityClick}
                />

                {/* Legend overlay */}
                {viewMode === "map" && (
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
                )}

                {/* Time Slider overlay */}
                <div className="kg-map-time-overlay">
                  <TimeSlider
                    min={yearRange.min}
                    max={yearRange.max}
                    value={currentYear}
                    isPlaying={isPlaying}
                    onChange={handleYearChange}
                    onPlayToggle={handlePlayToggle}
                  />
                </div>

                {/* Entity Popup */}
                {selectedEntity && (
                  <MapEntityPopup
                    entity={selectedEntity}
                    onClose={() => setSelectedEntity(null)}
                    onViewInGraph={handleViewInGraph}
                  />
                )}
              </>
            ) : (
              <LineageGraph
                arcs={arcData?.arcs ?? []}
                schoolFilter={schoolFilter}
                height={600}
                onNodeClick={handleViewInGraph}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
