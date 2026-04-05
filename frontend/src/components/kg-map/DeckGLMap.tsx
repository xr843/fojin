import { useState, useMemo, useCallback, useRef } from "react";
import { Map, type MapRef } from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import "maplibre-gl/dist/maplibre-gl.css";
import { escapeHtml } from "../../utils/sanitize";
import type { KGGeoEntity, KGLineageArc } from "../../api/client";

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

/** Light basemap — MapTiler Streets with Chinese labels */
const MAPTILER_KEY = "sBS5GCqJuftwymqkp64I";
const MAP_STYLE = `https://api.maptiler.com/maps/streets-v2/style.json?key=${MAPTILER_KEY}&language=zh`;

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

interface ArcTooltipState {
  x: number;
  y: number;
  arc: KGLineageArc;
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
  const [arcTooltip, setArcTooltip] = useState<ArcTooltipState | null>(null);
  const mapRef = useRef<MapRef>(null);

  /** Force Chinese labels after style loads */
  const handleMapLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const layers = map.getStyle().layers || [];
    for (const layer of layers) {
      if (layer.type === "symbol" && layer.layout && "text-field" in layer.layout) {
        try {
          map.setLayoutProperty(layer.id, "text-field", [
            "coalesce",
            ["get", "name:zh-Hans"],
            ["get", "name:zh"],
            ["get", "name:zh-Hant"],
            ["get", "name:ja"],
            ["get", "name_int"],
            ["get", "name:latin"],
            ["get", "name:en"],
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
        // Entities without year data are always shown (timeless features).
        // Only filter entities that explicitly fall outside the current year.
        if (e.year_start !== null || e.year_end !== null) {
          const start = e.year_start ?? e.year_end ?? -Infinity;
          const end = e.year_end ?? e.year_start ?? Infinity;
          if (currentYear < start || currentYear > end) return false;
        }
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

  const layers = useMemo(() => {
    const result = [];

    // Layered rendering: monastery → others → place → person (minority on top)
    const monasteries = filteredEntities.filter((e) => e.entity_type === "monastery");
    const places = filteredEntities.filter((e) => e.entity_type === "place");
    const persons = filteredEntities.filter((e) => e.entity_type === "person");
    const others = filteredEntities.filter(
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
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 215, 0, 220],
          onHover: (info: PickingInfo) => {
            if (info.object && info.x !== undefined && info.y !== undefined) {
              setArcTooltip({ x: info.x, y: info.y, arc: info.object as KGLineageArc });
            } else {
              setArcTooltip(null);
            }
          },
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
        useDevicePixels={true}
        style={{ position: "absolute", inset: "0" }}
      >
        <Map ref={mapRef} mapStyle={MAP_STYLE} onLoad={handleMapLoad} />
      </DeckGL>

      {tooltip && (() => {
        const e = tooltip.entity;
        const flag = detectCountryFlag(e.description, e.name_en, e.name_zh);
        const countryName = detectCountryName(e.description, e.name_en, e.name_zh);
        const script = detectScript(e.name_zh);
        const isLocalName = script !== 'cjk';
        const source = detectSource(e.description);
        return (
          <div
            className="kg-map-tooltip"
            style={{ left: tooltip.x + 12, top: tooltip.y - 12 }}
          >
            <div className="tooltip-header">
              <span className="tooltip-flag">{flag}</span>
              <span className="tooltip-type">
                {TYPE_LABEL_MAP[e.entity_type] || e.entity_type}
              </span>
            </div>
            <div
              className="tooltip-name"
              dangerouslySetInnerHTML={{ __html: escapeHtml(e.name_zh) }}
            />
            {e.name_en && (
              <div
                className="tooltip-en"
                dangerouslySetInnerHTML={{ __html: escapeHtml(e.name_en) }}
              />
            )}
            {isLocalName && countryName && (
              <div className="tooltip-local-notice">
                💡 本地名称 · 国家: {countryName}
              </div>
            )}
            {(e.year_start !== null || e.year_end !== null) && (
              <div className="tooltip-meta">
                📜 {formatYearRange(e.year_start, e.year_end)}
              </div>
            )}
            {e.description && (
              <div
                className="tooltip-desc"
                dangerouslySetInnerHTML={{ __html: escapeHtml(e.description) }}
              />
            )}
            {source && <div className="tooltip-source">数据: {source}</div>}
          </div>
        );
      })()}

      {arcTooltip && (
        <div
          className="kg-map-tooltip"
          style={{ left: arcTooltip.x + 12, top: arcTooltip.y - 12 }}
        >
          <div className="tooltip-header">
            <span className="tooltip-type">师承</span>
          </div>
          <div
            className="tooltip-name"
            dangerouslySetInnerHTML={{
              __html: `${escapeHtml(arcTooltip.arc.teacher_name)} → ${escapeHtml(arcTooltip.arc.student_name)}`,
            }}
          />
          {arcTooltip.arc.year !== null && (
            <div className="tooltip-meta">📜 {formatYear(arcTooltip.arc.year)}</div>
          )}
          {arcTooltip.arc.school && (
            <div
              className="tooltip-desc"
              dangerouslySetInnerHTML={{ __html: `宗派: ${escapeHtml(arcTooltip.arc.school)}` }}
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

const COUNTRY_FLAGS: Record<string, string> = {
  "中国": "🇨🇳", "China": "🇨🇳", "Chinese": "🇨🇳",
  "日本": "🇯🇵", "Japan": "🇯🇵", "Japanese": "🇯🇵",
  "韩国": "🇰🇷", "Korea": "🇰🇷", "Korean": "🇰🇷",
  "印度": "🇮🇳", "India": "🇮🇳", "Indian": "🇮🇳",
  "泰国": "🇹🇭", "Thailand": "🇹🇭", "Thai": "🇹🇭",
  "越南": "🇻🇳", "Vietnam": "🇻🇳", "Vietnamese": "🇻🇳",
  "缅甸": "🇲🇲", "Myanmar": "🇲🇲", "Burmese": "🇲🇲",
  "斯里兰卡": "🇱🇰", "Sri Lanka": "🇱🇰",
  "柬埔寨": "🇰🇭", "Cambodia": "🇰🇭",
  "西藏": "🏔️", "Tibet": "🏔️", "Tibetan": "🏔️",
  "蒙古": "🇲🇳", "Mongolia": "🇲🇳",
  "不丹": "🇧🇹", "Bhutan": "🇧🇹",
  "尼泊尔": "🇳🇵", "Nepal": "🇳🇵",
  "美国": "🇺🇸", "United States": "🇺🇸", "American": "🇺🇸",
  "德国": "🇩🇪", "Germany": "🇩🇪", "German": "🇩🇪",
  "法国": "🇫🇷", "France": "🇫🇷", "French": "🇫🇷",
  "英国": "🇬🇧", "British": "🇬🇧",
  "台湾": "🇹🇼", "Taiwan": "🇹🇼",
  "巴西": "🇧🇷", "Brazil": "🇧🇷",
  "澳大利亚": "🇦🇺", "Australia": "🇦🇺",
};

const COUNTRY_NAMES_ZH: Record<string, string> = {
  "中国": "中国", "China": "中国", "Chinese": "中国",
  "日本": "日本", "Japan": "日本", "Japanese": "日本",
  "韩国": "韩国", "Korea": "韩国", "Korean": "韩国",
  "印度": "印度", "India": "印度", "Indian": "印度",
  "泰国": "泰国", "Thailand": "泰国", "Thai": "泰国",
  "越南": "越南", "Vietnam": "越南", "Vietnamese": "越南",
  "缅甸": "缅甸", "Myanmar": "缅甸", "Burmese": "缅甸",
  "斯里兰卡": "斯里兰卡", "Sri Lanka": "斯里兰卡",
  "柬埔寨": "柬埔寨", "Cambodia": "柬埔寨",
  "西藏": "西藏", "Tibet": "西藏", "Tibetan": "西藏",
  "蒙古": "蒙古", "Mongolia": "蒙古",
  "不丹": "不丹", "Bhutan": "不丹",
  "尼泊尔": "尼泊尔", "Nepal": "尼泊尔",
  "美国": "美国", "United States": "美国", "American": "美国",
  "德国": "德国", "Germany": "德国", "German": "德国",
  "法国": "法国", "France": "法国", "French": "法国",
  "英国": "英国", "British": "英国",
  "台湾": "台湾", "Taiwan": "台湾",
  "巴西": "巴西", "Brazil": "巴西",
  "澳大利亚": "澳大利亚", "Australia": "澳大利亚",
};

function detectCountryFlag(
  desc: string | null,
  nameEn: string | null,
  nameZh: string,
): string {
  const haystack = `${desc ?? ""} ${nameEn ?? ""} ${nameZh}`;
  for (const key of Object.keys(COUNTRY_FLAGS)) {
    if (haystack.includes(key)) return COUNTRY_FLAGS[key];
  }
  return "🏛️";
}

function detectCountryName(
  desc: string | null,
  nameEn: string | null,
  nameZh: string,
): string | null {
  const haystack = `${desc ?? ""} ${nameEn ?? ""} ${nameZh}`;
  for (const key of Object.keys(COUNTRY_NAMES_ZH)) {
    if (haystack.includes(key)) return COUNTRY_NAMES_ZH[key];
  }
  return null;
}

function detectScript(s: string): 'cjk' | 'hangul' | 'latin' | 'other' {
  if (/[\uAC00-\uD7AF]/.test(s)) return 'hangul';
  if (/[\u4E00-\u9FFF\u3040-\u30FF]/.test(s)) return 'cjk';
  if (/[a-zA-Z]/.test(s)) return 'latin';
  return 'other';
}

function detectSource(desc: string | null): string | null {
  if (!desc) return null;
  const sources = ["OSM", "OpenStreetMap", "Wikidata", "DILA", "BDRC", "GeoNames"];
  for (const s of sources) {
    if (desc.includes(s)) return s === "OpenStreetMap" ? "OSM" : s;
  }
  return null;
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
