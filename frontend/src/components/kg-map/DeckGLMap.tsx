import { useState, useMemo, useCallback } from "react";
import { Map } from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import "maplibre-gl/dist/maplibre-gl.css";
import { escapeHtml } from "../../utils/sanitize";
import type { KGGeoEntity, KGLineageArc } from "../../api/client";

/** FoJin classical color palette — RGB tuples for deck.gl */
const TYPE_COLORS: Record<string, [number, number, number]> = {
  person: [199, 84, 80],       // 朱砂
  text: [74, 124, 155],        // 靛青
  monastery: [107, 142, 91],   // 松绿
  school: [123, 94, 167],      // 紫藤
  place: [192, 139, 62],       // 赭石
  concept: [61, 138, 138],     // 青碧
  dynasty: [179, 92, 138],     // 洋紫
};

const INITIAL_VIEW_STATE = {
  longitude: 85,
  latitude: 25,
  zoom: 3,
  pitch: 0,
  bearing: 0,
};

const MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

interface DeckGLMapProps {
  geoEntities: KGGeoEntity[];
  lineageArcs: KGLineageArc[];
  showArcs: boolean;
  currentYear: number | null;
  entityTypeFilter: string[];
  onEntityClick: (entity: KGGeoEntity) => void;
}

interface TooltipState {
  x: number;
  y: number;
  entity: KGGeoEntity;
}

export default function DeckGLMap({
  geoEntities,
  lineageArcs,
  showArcs,
  currentYear,
  entityTypeFilter,
  onEntityClick,
}: DeckGLMapProps) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  /** Filter entities by type and time (client-side) */
  const filteredEntities = useMemo(() => {
    return geoEntities.filter((e) => {
      if (!entityTypeFilter.includes(e.entity_type)) return false;
      if (currentYear !== null) {
        const start = e.year_start ?? -Infinity;
        const end = e.year_end ?? Infinity;
        if (currentYear < start || currentYear > end) return false;
      }
      return true;
    });
  }, [geoEntities, entityTypeFilter, currentYear]);

  /** Filter arcs by time */
  const filteredArcs = useMemo(() => {
    if (!showArcs) return [];
    return lineageArcs.filter((a) => {
      if (currentYear === null) return true;
      if (a.year === null) return true;
      return Math.abs(a.year - currentYear) <= 100;
    });
  }, [lineageArcs, showArcs, currentYear]);

  const handleHover = useCallback((info: PickingInfo) => {
    if (info.object && info.x !== undefined && info.y !== undefined) {
      setTooltip({ x: info.x, y: info.y, entity: info.object as KGGeoEntity });
    } else {
      setTooltip(null);
    }
  }, []);

  const handleClick = useCallback(
    (info: PickingInfo) => {
      if (info.object) {
        onEntityClick(info.object as KGGeoEntity);
      }
    },
    [onEntityClick],
  );

  const layers = useMemo(() => {
    const result = [];

    result.push(
      new ScatterplotLayer<KGGeoEntity>({
        id: "entities",
        data: filteredEntities,
        getPosition: (d) => [d.longitude, d.latitude],
        getFillColor: (d) => TYPE_COLORS[d.entity_type] ?? [128, 128, 128],
        getRadius: 6000,
        radiusMinPixels: 4,
        radiusMaxPixels: 16,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 200, 60, 160],
        onHover: handleHover,
        onClick: handleClick,
        updateTriggers: {
          getPosition: [filteredEntities],
          getFillColor: [filteredEntities],
        },
      }),
    );

    if (showArcs && filteredArcs.length > 0) {
      result.push(
        new ArcLayer<KGLineageArc>({
          id: "lineage-arcs",
          data: filteredArcs,
          getSourcePosition: (d) => [d.teacher_lng, d.teacher_lat],
          getTargetPosition: (d) => [d.student_lng, d.student_lat],
          getSourceColor: [192, 139, 62, 180],  // 赭石
          getTargetColor: [199, 84, 80, 180],    // 朱砂
          getWidth: 1.5,
          greatCircle: true,
        }),
      );
    }

    return result;
  }, [filteredEntities, filteredArcs, showArcs, handleHover, handleClick]);

  return (
    <>
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller
        layers={layers}
        style={{ position: "absolute", inset: "0" }}
      >
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>

      {tooltip && (
        <div
          className="kg-map-tooltip"
          style={{ left: tooltip.x + 12, top: tooltip.y - 12 }}
        >
          <div
            className="tooltip-name"
            dangerouslySetInnerHTML={{ __html: escapeHtml(tooltip.entity.name_zh) }}
          />
          {tooltip.entity.name_en && (
            <div
              className="tooltip-en"
              dangerouslySetInnerHTML={{ __html: escapeHtml(tooltip.entity.name_en) }}
            />
          )}
          <div className="tooltip-type">
            {TYPE_LABEL_MAP[tooltip.entity.entity_type] || tooltip.entity.entity_type}
          </div>
          {(tooltip.entity.year_start !== null || tooltip.entity.year_end !== null) && (
            <div className="tooltip-year">
              {formatYearRange(tooltip.entity.year_start, tooltip.entity.year_end)}
            </div>
          )}
        </div>
      )}
    </>
  );
}

/* ---------- helpers ---------- */

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

const TYPE_LABEL_MAP: Record<string, string> = {
  person: "人物",
  text: "典籍",
  monastery: "寺院",
  school: "宗派",
  place: "地点",
  concept: "概念",
  dynasty: "朝代",
};
