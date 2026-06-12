import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import { Map, type MapRef } from "react-map-gl/maplibre";
import type { StyleSpecification } from "maplibre-gl";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import "maplibre-gl/dist/maplibre-gl.css";
import { escapeHtml } from "../../utils/sanitize";
import type { KGGeoEntity, KGLineageArc } from "../../api/client";

/** Bright, highly-distinct palette for light background */
const TYPE_COLORS: Record<string, [number, number, number]> = {
  person:    [220, 38, 38],    // 鲜红 (red-600)
  monastery: [34, 197, 94],    // 鲜绿 (green-500)
  place:     [124, 58, 237],   // 鲜紫 (violet-600)
  school:    [37, 99, 235],    // 蓝 (blue-600)
  text:      [6, 182, 212],    // 青 (cyan-500)
  concept:   [8, 145, 178],    // 深青
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
  focusEntity?: KGGeoEntity | null;
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
  focusEntity,
}: DeckGLMapProps) {
  const { t } = useTranslation();
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [arcTooltip, setArcTooltip] = useState<ArcTooltipState | null>(null);
  const [viewState, setViewState] = useState<typeof INITIAL_VIEW_STATE & { transitionDuration?: number }>(INITIAL_VIEW_STATE);
  const mapRef = useRef<MapRef>(null);

  // Fly to focused entity when it changes
  useEffect(() => {
    if (!focusEntity || focusEntity.longitude == null || focusEntity.latitude == null) return;
    setViewState((prev) => ({
      ...prev,
      longitude: focusEntity.longitude,
      latitude: focusEntity.latitude,
      zoom: Math.max(prev.zoom, 9),
      transitionDuration: 1200,
    }));
  }, [focusEntity]);

  // Pulse animation for highlight ring
  const [pulseScale, setPulseScale] = useState(1.0);
  useEffect(() => {
    if (!focusEntity) return;
    let frame: number;
    const start = performance.now();
    const animate = () => {
      const t = ((performance.now() - start) % 1200) / 1200;
      setPulseScale(1.0 + 0.5 * Math.sin(t * Math.PI * 2));
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [focusEntity]);

  /** Fetch + patch MapTiler style to force zh labels and replace Taiwan name */
  const [patchedStyle, setPatchedStyle] = useState<StyleSpecification | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(MAP_STYLE)
      .then((r) => r.json())
      .then((style: { layers?: Array<{ id: string; type: string; layout?: Record<string, unknown> }> }) => {
        if (cancelled || !style.layers) return;
        const twReplace = [
          "case",
          ["==", ["get", "iso_a2"], "TW"], "台灣省", // i18n-exempt
          ["==", ["get", "ISO_A2"], "TW"], "台灣省", // i18n-exempt
          ["==", ["get", "iso_3166_1"], "TW"], "台灣省", // i18n-exempt
          ["==", ["get", "iso_3166_1_alpha_2"], "TW"], "台灣省", // i18n-exempt
          ["==", ["get", "name"], "中華民國"], "台灣省", // i18n-exempt
          ["==", ["get", "name"], "中华民国"], "台灣省", // i18n-exempt
          ["==", ["get", "name"], "Taiwan"], "台灣省", // i18n-exempt
          ["==", ["get", "name"], "Republic of China"], "台灣省", // i18n-exempt
          ["==", ["get", "name:zh"], "中華民國"], "台灣省", // i18n-exempt
          ["==", ["get", "name:zh"], "中华民国"], "台灣省", // i18n-exempt
          ["==", ["get", "name:zh-Hant"], "中華民國"], "台灣省", // i18n-exempt
          ["==", ["get", "name:zh-Hant"], "臺灣"], "台灣省", // i18n-exempt
          ["==", ["get", "name:zh-Hant"], "台灣"], "台灣省", // i18n-exempt
          ["==", ["get", "name:zh-Hans"], "中华民国"], "台灣省", // i18n-exempt
          ["==", ["get", "name:zh-Hans"], "台湾"], "台灣省", // i18n-exempt
          ["==", ["get", "name:en"], "Taiwan"], "台灣省", // i18n-exempt
          ["==", ["get", "name:en"], "Republic of China"], "台灣省", // i18n-exempt
          [
            "coalesce",
            ["get", "name:zh-Hans"],
            ["get", "name:zh"],
            ["get", "name:zh-Hant"],
            ["get", "name:ja"],
            ["get", "name_int"],
            ["get", "name:latin"],
            ["get", "name:en"],
            ["get", "name"],
          ],
        ];
        for (const layer of style.layers) {
          if (layer.type !== "symbol" || !layer.layout) continue;
          if (!("text-field" in layer.layout)) continue;
          const orig = JSON.stringify(layer.layout["text-field"] ?? "");
          if (!orig.includes("name")) continue;
          layer.layout["text-field"] = twReplace;
        }
        setPatchedStyle(style as unknown as StyleSpecification);
      })
      .catch((e) => {
        console.error("[style fetch err]", e);
      });
    return () => {
      cancelled = true;
    };
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
      const hovered = info.object as KGGeoEntity;
      // If a focused entity exists and the hovered entity is at the same location,
      // show the focused entity in tooltip to avoid confusion
      if (focusEntity && focusEntity.id !== hovered.id &&
          Math.abs(hovered.latitude - focusEntity.latitude) < 0.001 &&
          Math.abs(hovered.longitude - focusEntity.longitude) < 0.001) {
        setTooltip({ x: info.x, y: info.y, entity: focusEntity });
      } else {
        setTooltip({ x: info.x, y: info.y, entity: hovered });
      }
    } else {
      setTooltip(null);
    }
  }, [focusEntity]);

  const handleClick = useCallback(
    (info: PickingInfo) => {
      if (!info.object) return;
      const clicked = info.object as KGGeoEntity;
      // If focused entity is at the same location, select the focused one
      if (focusEntity && focusEntity.id !== clicked.id &&
          Math.abs(clicked.latitude - focusEntity.latitude) < 0.001 &&
          Math.abs(clicked.longitude - focusEntity.longitude) < 0.001) {
        onEntityClick(focusEntity);
      } else {
        onEntityClick(clicked);
      }
    },
    [onEntityClick, focusEntity],
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

    // Highlight ring for focused/selected entity (pulsing)
    if (focusEntity) {
      result.push(
        new ScatterplotLayer<KGGeoEntity>({
          id: "highlight-pulse",
          data: [focusEntity],
          getPosition: (d) => [d.longitude, d.latitude],
          getFillColor: [255, 69, 0, 40],
          getLineColor: [255, 69, 0, Math.round(120 + 80 * (pulseScale - 1))],
          stroked: true,
          lineWidthMinPixels: 2.5,
          getRadius: 8000,
          radiusScale: pulseScale,
          radiusMinPixels: Math.round(12 * pulseScale),
          radiusMaxPixels: Math.round(22 * pulseScale),
          pickable: false,
          updateTriggers: {
            getLineColor: [pulseScale],
            radiusScale: [pulseScale],
          },
        }),
      );
    }

    // Lineage arcs
    if (showArcs && filteredArcs.length > 0) {
      result.push(
        new ArcLayer<KGLineageArc>({
          id: "lineage-arcs",
          data: filteredArcs,
          getSourcePosition: (d) => [d.teacher_lng, d.teacher_lat],
          getTargetPosition: (d) => [d.student_lng, d.student_lat],
          getSourceColor: [234, 179, 8, 200],
          getTargetColor: [234, 179, 8, 200],
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
  }, [filteredEntities, filteredArcs, showArcs, handleHover, handleClick, focusEntity, pulseScale]);

  return (
    <>
      <DeckGL
        viewState={viewState}
        onViewStateChange={(e) => setViewState(e.viewState as typeof viewState)}
        controller
        layers={layers}
        useDevicePixels={true}
        style={{ position: "absolute", inset: "0" }}
      >
        {patchedStyle && <Map ref={mapRef} mapStyle={patchedStyle} />}
      </DeckGL>

      {tooltip && (() => {
        const e = tooltip.entity;
        const flag = detectCountryFlag(e.description, e.name_en, e.name_zh);
        const countryName = detectCountryName(e.description, e.name_en, e.name_zh);
        // Country names are canonical zh data values — translate at display time.
        const countryLabel = countryName
          ? t(COUNTRY_KEY_OVERRIDES[countryName] ?? `region.${countryName}`, countryName)
          : null;
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
                {TYPE_LABEL_KEYS[e.entity_type] ? t(TYPE_LABEL_KEYS[e.entity_type]) : e.entity_type}
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
            {isLocalName && countryLabel && (
              <div className="tooltip-local-notice">
                {t("geo.local_name_country", { name: countryLabel })}
              </div>
            )}
            {(e.year_start !== null || e.year_end !== null) && (
              <div className="tooltip-meta">
                📜 {formatYearRange(t, e.year_start, e.year_end)}
              </div>
            )}
            {e.description && (
              <div
                className="tooltip-desc"
                dangerouslySetInnerHTML={{ __html: escapeHtml(e.description) }}
              />
            )}
            {source && <div className="tooltip-source">{t("geo.data_source", { name: source })}</div>}
          </div>
        );
      })()}

      {arcTooltip && (
        <div
          className="kg-map-tooltip"
          style={{ left: arcTooltip.x + 12, top: arcTooltip.y - 12 }}
        >
          <div className="tooltip-header">
            <span className="tooltip-type">{t("geo.lineage")}</span>
          </div>
          <div
            className="tooltip-name"
            dangerouslySetInnerHTML={{
              __html: `${escapeHtml(arcTooltip.arc.teacher_name)} → ${escapeHtml(arcTooltip.arc.student_name)}`,
            }}
          />
          {arcTooltip.arc.year !== null && (
            <div className="tooltip-meta">📜 {formatYear(t, arcTooltip.arc.year)}</div>
          )}
          {arcTooltip.arc.school && (
            <div
              className="tooltip-desc"
              dangerouslySetInnerHTML={{ __html: `${escapeHtml(t("geo.school_label"))}: ${escapeHtml(arcTooltip.arc.school)}` }}
            />
          )}
        </div>
      )}
    </>
  );
}

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

/** Match-term → canonical zh country name. Values are matching/lookup data
    (haystack.includes), translated at display time via `region.*` keys with
    COUNTRY_KEY_OVERRIDES for names whose region.* zh value differs. */
const COUNTRY_NAMES_ZH: Record<string, string> = {
  "中国": "中国", "China": "中国", "Chinese": "中国", // i18n-exempt
  "日本": "日本", "Japan": "日本", "Japanese": "日本", // i18n-exempt
  "韩国": "韩国", "Korea": "韩国", "Korean": "韩国", // i18n-exempt
  "印度": "印度", "India": "印度", "Indian": "印度", // i18n-exempt
  "泰国": "泰国", "Thailand": "泰国", "Thai": "泰国", // i18n-exempt
  "越南": "越南", "Vietnam": "越南", "Vietnamese": "越南", // i18n-exempt
  "缅甸": "缅甸", "Myanmar": "缅甸", "Burmese": "缅甸", // i18n-exempt
  "斯里兰卡": "斯里兰卡", "Sri Lanka": "斯里兰卡", // i18n-exempt
  "柬埔寨": "柬埔寨", "Cambodia": "柬埔寨", // i18n-exempt
  "西藏": "西藏", "Tibet": "西藏", "Tibetan": "西藏", // i18n-exempt
  "蒙古": "蒙古", "Mongolia": "蒙古", // i18n-exempt
  "不丹": "不丹", "Bhutan": "不丹", // i18n-exempt
  "尼泊尔": "尼泊尔", "Nepal": "尼泊尔", // i18n-exempt
  "美国": "美国", "United States": "美国", "American": "美国", // i18n-exempt
  "德国": "德国", "Germany": "德国", "German": "德国", // i18n-exempt
  "法国": "法国", "France": "法国", "French": "法国", // i18n-exempt
  "英国": "英国", "British": "英国", // i18n-exempt
  "台湾": "台湾", "Taiwan": "台湾", // i18n-exempt
  "巴西": "巴西", "Brazil": "巴西", // i18n-exempt
  "澳大利亚": "澳大利亚", "Australia": "澳大利亚", // i18n-exempt
};

/** zh country names whose `region.*` locale entry has a DIFFERENT zh value
    (e.g. region.中国 renders 中国大陆) — these use dedicated geo.* keys so the
    zh tooltip stays byte-identical. */
const COUNTRY_KEY_OVERRIDES: Record<string, string> = {
  "中国": "geo.country_cn",
  "西藏": "geo.country_tibet",
  "台湾": "geo.country_tw",
  "巴西": "geo.country_br",
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

const TYPE_LABEL_KEYS: Record<string, string> = {
  person: "geo.type_person",
  text: "geo.type_text",
  monastery: "geo.type_temple",
  school: "geo.type_school",
  place: "geo.type_place",
  concept: "geo.type_concept",
  dynasty: "geo.type_dynasty",
};
