import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Checkbox, Spin, Empty, Tooltip } from "antd";
import { GlobalOutlined, BarChartOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import DeckGLMap from "../components/kg-map/DeckGLMap";
import MapEntityPopup from "../components/kg-map/MapEntityPopup";
import TimeSlider from "../components/kg-map/TimeSlider";
import { getKGStats, getKGGeoEntities, getKGLineageArcs } from "../api/client";
import type { KGGeoEntity } from "../api/client";
import "../styles/kg-map.css";

const ENTITY_TYPE_OPTIONS = [
  { value: "monastery", label: "寺院" },
  { value: "place", label: "地点" },
  { value: "person", label: "人物" },
  { value: "school", label: "宗派" },
];

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

  /* ---------- Queries ---------- */

  const { data: kgStats } = useQuery({
    queryKey: ["kg-stats"],
    queryFn: getKGStats,
    staleTime: 60_000,
  });

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
        {kgStats && (
          <Tooltip title="数据统计">
            <span className="kg-map-stats">
              <BarChartOutlined />
              <span>
                {kgStats.total_entities.toLocaleString()} 实体 /{" "}
                {kgStats.total_relations.toLocaleString()} 关系
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
              geoEntities={geoData.entities}
              lineageArcs={arcData?.arcs ?? []}
              showArcs={showArcs}
              currentYear={currentYear}
              entityTypeFilter={entityTypes}
              onEntityClick={handleEntityClick}
            />

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
        )}
      </div>
    </div>
  );
}
