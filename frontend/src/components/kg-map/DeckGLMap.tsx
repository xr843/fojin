import { useState, useMemo, useCallback, useRef } from "react";
import { Map, type MapRef } from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer, ArcLayer, TextLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import Supercluster from "supercluster";
import type { PointFeature, ClusterFeature } from "supercluster";
import "maplibre-gl/dist/maplibre-gl.css";
import { escapeHtml } from "../../utils/sanitize";
import type { KGGeoEntity, KGLineageArc } from "../../api/client";

type EntityProps = { entity: KGGeoEntity };
type AnyFeature = PointFeature<EntityProps> | ClusterFeature<EntityProps>;

/** Bright, highly-distinct palette for light background */
const TYPE_COLORS: Record<string, [number, number, number]> = {
  person:    [220, 38, 38],    // 鲜红 (red-600)
  monastery: [34, 197, 94],    // 鲜绿 (green-500)
  place:     [124, 58, 237],   // 鲜紫 (violet-600)
  school:    [234, 88, 12],    // 橙 (orange-600)
  text:      [37, 99, 235],    // 蓝 (blue-600)
  concept:   [8, 145, 178],    // 青 (cyan-600)
  dynasty:   [219, 39, 119],   // 洋红 (pink-600)
};

const INITIAL_VIEW_STATE = {
  longitude: 115,
  latitude: 35,
  zoom: 4.2,
  pitch: 0,
  bearing: 0,
};

/** Light basemap — CARTO Voyager */
const MAP_STYLE = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json";

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
  const [viewState, setViewState] = useState<typeof INITIAL_VIEW_STATE & { transitionDuration?: number }>(INITIAL_VIEW_STATE);
  const mapRef = useRef<MapRef>(null);

  /** Switch map labels to Chinese (prefer name:zh, fallback to name) */
  const handleMapLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const layers = map.getStyle().layers || [];
    for (const layer of layers) {
      if (layer.type === "symbol" && layer.layout && "text-field" in layer.layout) {
        try {
          map.setLayoutProperty(layer.id, "text-field", [
            "coalesce",
            ["get", "name:zh"],
            ["get", "name_zh"],
            ["get", "name:zh-Hans"],
            ["get", "name_int"],
            ["get", "name"],
          ]);
        } catch {
          // skip layers that don't support this
        }
      }
    }
  }, []);

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
      if (info.object) onEntityClick(info.object as KGGeoEntity);
    },
    [onEntityClick],
  );

  // Build supercluster index from filtered entities
  const clusterIndex = useMemo(() => {
    const index = new Supercluster<EntityProps, Record<string, never>>({
      radius: 40,
      maxZoom: 12,
      minPoints: 3,
    });
    const points: PointFeature<EntityProps>[] = filteredEntities.map((e) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [e.longitude, e.latitude] },
      properties: { entity: e },
    }));
    index.load(points);
    return index;
  }, [filteredEntities]);

  // Get clusters at current zoom
  const clusters = useMemo(() => {
    const bbox: [number, number, number, number] = [-180, -85, 180, 85];
    return clusterIndex.getClusters(bbox, Math.floor(viewState.zoom)) as AnyFeature[];
  }, [clusterIndex, viewState.zoom]);

  const handleClusterClick = useCallback(
    (info: PickingInfo) => {
      const obj = info.object as ClusterFeature<EntityProps> | undefined;
      if (!obj || !obj.properties.cluster) return;
      const clusterId = obj.properties.cluster_id;
      const expansionZoom = clusterIndex.getClusterExpansionZoom(clusterId);
      const [lng, lat] = obj.geometry.coordinates;
      setViewState({
        ...viewState,
        longitude: lng,
        latitude: lat,
        zoom: Math.min(expansionZoom, 15),
        transitionDuration: 500,
      });
    },
    [clusterIndex, viewState],
  );

  const layers = useMemo(() => {
    const result = [];

    // Separate clusters from individual points
    const clusterPoints = clusters.filter(
      (c): c is ClusterFeature<EntityProps> => Boolean(c.properties && (c.properties as { cluster?: boolean }).cluster),
    );
    const individualEntities: KGGeoEntity[] = clusters
      .filter((c) => !(c.properties as { cluster?: boolean }).cluster)
      .map((c) => (c.properties as EntityProps).entity);

    // Cluster circle layer
    if (clusterPoints.length) {
      result.push(
        new ScatterplotLayer<ClusterFeature<EntityProps>>({
          id: "clusters",
          data: clusterPoints,
          getPosition: (d) => d.geometry.coordinates as [number, number],
          getRadius: (d) => {
            const count = d.properties.point_count;
            return 10000 + Math.log(count) * 4000;
          },
          getFillColor: [124, 58, 237, 180],
          getLineColor: [255, 255, 255, 220],
          lineWidthMinPixels: 2,
          stroked: true,
          radiusMinPixels: 20,
          radiusMaxPixels: 60,
          pickable: true,
          onClick: handleClusterClick,
        }),
      );

      result.push(
        new TextLayer<ClusterFeature<EntityProps>>({
          id: "cluster-labels",
          data: clusterPoints,
          getPosition: (d) => d.geometry.coordinates as [number, number],
          getText: (d) => String(d.properties.point_count_abbreviated ?? d.properties.point_count),
          getSize: 14,
          getColor: [255, 255, 255, 255],
          fontFamily: "system-ui, sans-serif",
          fontWeight: 700,
          getTextAnchor: "middle",
          getAlignmentBaseline: "center",
          pickable: false,
        }),
      );
    }

    // Layered rendering (individual points only): monastery → place → person
    const monasteries = individualEntities.filter((e) => e.entity_type === "monastery");
    const places = individualEntities.filter((e) => e.entity_type === "place");
    const persons = individualEntities.filter((e) => e.entity_type === "person");
    const others = individualEntities.filter(
      (e) => !["monastery", "place", "person"].includes(e.entity_type),
    );

    const makeLayer = (id: string, data: KGGeoEntity[]) =>
      new ScatterplotLayer<KGGeoEntity>({
        id,
        data,
        getPosition: (d) => [d.longitude, d.latitude],
        getFillColor: (d) => {
          const c = TYPE_COLORS[d.entity_type] ?? [128, 128, 128];
          return [c[0], c[1], c[2], 200];
        },
        getLineColor: [255, 255, 255, 220],
        lineWidthMinPixels: 0.5,
        stroked: true,
        getRadius: 2500,
        radiusMinPixels: 3,
        radiusMaxPixels: 9,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 215, 0, 220],
        onHover: handleHover,
        onClick: handleClick,
      });

    // Z-order: monastery (bottom) → others → place → person (top)
    if (monasteries.length) result.push(makeLayer("entities-monastery", monasteries));
    if (others.length) result.push(makeLayer("entities-others", others));
    if (places.length) result.push(makeLayer("entities-place", places));
    if (persons.length) result.push(makeLayer("entities-person", persons));

    // Lineage arcs
    if (showArcs && filteredArcs.length > 0) {
      result.push(
        new ArcLayer<KGLineageArc>({
          id: "lineage-arcs",
          data: filteredArcs,
          getSourcePosition: (d) => [d.teacher_lng, d.teacher_lat],
          getTargetPosition: (d) => [d.student_lng, d.student_lat],
          getSourceColor: [200, 140, 45, 180],
          getTargetColor: [210, 60, 50, 180],
          getWidth: 1.5,
          greatCircle: true,
        }),
      );
    }

    return result;
  }, [clusters, filteredArcs, showArcs, handleHover, handleClick, handleClusterClick]);

  return (
    <>
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState: vs }) => setViewState(vs as typeof INITIAL_VIEW_STATE)}
        controller
        layers={layers}
        style={{ position: "absolute", inset: "0" }}
      >
        <Map ref={mapRef} mapStyle={MAP_STYLE} onLoad={handleMapLoad} />
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
          {tooltip.entity.description && (
            <div
              className="tooltip-desc"
              dangerouslySetInnerHTML={{ __html: escapeHtml(tooltip.entity.description) }}
            />
          )}
        </div>
      )}
    </>
  );
}

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
