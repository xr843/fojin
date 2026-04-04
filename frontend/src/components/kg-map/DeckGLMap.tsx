import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { Map } from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import "maplibre-gl/dist/maplibre-gl.css";
import { escapeHtml } from "../../utils/sanitize";
import type { KGGeoEntity, KGLineageArc } from "../../api/client";

/** FoJin classical palette — brighter for dark background */
const TYPE_COLORS: Record<string, [number, number, number]> = {
  person:    [255, 110, 100],  // 朱砂 (brighter)
  text:      [100, 170, 220],  // 靛青
  monastery: [140, 200, 120],  // 松绿
  school:    [170, 130, 230],  // 紫藤
  place:     [240, 180, 80],   // 赭石
  concept:   [80, 200, 200],   // 青碧
  dynasty:   [220, 120, 180],  // 洋紫
};

const INITIAL_VIEW_STATE = {
  longitude: 90,
  latitude: 28,
  zoom: 3.5,
  pitch: 0,
  bearing: 0,
};

/** Dark basemap — CARTO dark-matter (no labels variant for cleaner look) */
const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json";

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
  const [pulsePhase, setPulsePhase] = useState(0);
  const rafRef = useRef<number>(0);

  /** Pulse animation loop — drives the outer glow ring */
  useEffect(() => {
    let frame = 0;
    const animate = () => {
      frame++;
      // Update every 3 frames (~20fps) to save CPU
      if (frame % 3 === 0) {
        setPulsePhase(Date.now() * 0.001);
      }
      rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

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

  /** Compute animated pulse multiplier (0.8 — 2.5) */
  const pulseScale = 1.5 + Math.sin(pulsePhase * 2) * 0.8;
  const pulseOpacity = Math.max(0, 0.4 - Math.sin(pulsePhase * 2) * 0.3);

  const layers = useMemo(() => {
    const result = [];

    // Layer 1: Outer glow ring (animated pulse)
    result.push(
      new ScatterplotLayer<KGGeoEntity>({
        id: "entities-glow",
        data: filteredEntities,
        getPosition: (d) => [d.longitude, d.latitude],
        getFillColor: (d) => {
          const c = TYPE_COLORS[d.entity_type] ?? [128, 128, 128];
          return [c[0], c[1], c[2], Math.round(pulseOpacity * 255)];
        },
        getRadius: 12000 * pulseScale,
        radiusMinPixels: 8 * pulseScale,
        radiusMaxPixels: 40,
        pickable: false,
        updateTriggers: {
          getRadius: [pulseScale],
          getFillColor: [pulseOpacity],
        },
      }),
    );

    // Layer 2: Mid glow (softer, slightly animated)
    result.push(
      new ScatterplotLayer<KGGeoEntity>({
        id: "entities-mid-glow",
        data: filteredEntities,
        getPosition: (d) => [d.longitude, d.latitude],
        getFillColor: (d) => {
          const c = TYPE_COLORS[d.entity_type] ?? [128, 128, 128];
          return [c[0], c[1], c[2], 60];
        },
        getRadius: 9000,
        radiusMinPixels: 7,
        radiusMaxPixels: 28,
        pickable: false,
      }),
    );

    // Layer 3: Core dot (solid, bright)
    result.push(
      new ScatterplotLayer<KGGeoEntity>({
        id: "entities-core",
        data: filteredEntities,
        getPosition: (d) => [d.longitude, d.latitude],
        getFillColor: (d) => {
          const c = TYPE_COLORS[d.entity_type] ?? [128, 128, 128];
          return [c[0], c[1], c[2], 240];
        },
        getRadius: 4000,
        radiusMinPixels: 3,
        radiusMaxPixels: 12,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 200, 180],
        onHover: handleHover,
        onClick: handleClick,
      }),
    );

    // Layer 4: Lineage arcs (glowing)
    if (showArcs && filteredArcs.length > 0) {
      result.push(
        new ArcLayer<KGLineageArc>({
          id: "lineage-arcs",
          data: filteredArcs,
          getSourcePosition: (d) => [d.teacher_lng, d.teacher_lat],
          getTargetPosition: (d) => [d.student_lng, d.student_lat],
          getSourceColor: [240, 180, 80, 200],   // 赭石 — teacher
          getTargetColor: [255, 110, 100, 200],   // 朱砂 — student
          getWidth: 2,
          greatCircle: true,
        }),
      );
    }

    return result;
  }, [filteredEntities, filteredArcs, showArcs, pulseScale, pulseOpacity, handleHover, handleClick]);

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
