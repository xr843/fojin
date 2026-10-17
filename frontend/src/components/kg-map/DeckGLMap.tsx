import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import { Map, Source, Layer, useControl, type MapRef, type ViewStateChangeEvent } from "react-map-gl/maplibre";
import type { StyleSpecification, SkySpecification } from "maplibre-gl";
import { MapLibreOverlay, type MapLibreOverlayProps } from "@deck.gl/maplibre";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import "maplibre-gl/dist/maplibre-gl.css";
import { escapeHtml } from "../../utils/sanitize";
import { useEffectiveTheme } from "../../hooks/useTheme";
import { typeColors } from "./typeColors";
import { collapseAttributionIfNarrow } from "./mapAttribution";
import { useNarrowViewport } from "../../hooks/useNarrowViewport";
import type { KGGeoEntity, KGLineageArc } from "../../api/client";

/** Same breakpoint as the mobile block in kg-map.css. */
const PHONE_QUERY = "(max-width: 768px)";
/** Below this zoom every dot is clamped to radiusMinPixels (2.5 km ≪ 1 px), so on a
 *  phone-width map 65k dots tile eastern China solid and bury the city labels. */
const DENSE_ZOOM = 6;

const INITIAL_VIEW_STATE = {
  longitude: 115,
  latitude: 35,
  zoom: 4.2,
  pitch: 0,
  bearing: 0,
};

/** 立体视角的镜头：斜 55°、略向西偏 15°；3D 下允许手动压到 70°（远处有天空与雾）。 */
const PITCH_3D = 55;
const BEARING_3D = -15;
const MAX_PITCH_3D = 70;
const VIEW_TRANSITION_MS = 900;

/** 地形夸张系数。东亚全图（zoom 4–5）下 1 倍高差几乎看不出起伏；1.6 倍让青藏高原、
 *  横断山、秦岭立得起来，又不至于把山画成针。点的 z 必须乘同一个系数，否则点会悬空/入地。 */
const TERRAIN_EXAGGERATION = 1.6;
const DEM_SOURCE_ID = "fojin-dem";
const HILLSHADE_SOURCE_ID = "fojin-dem-hillshade";
/** 高程与渲染同源：MapTiler terrain-rgb-v2。点的海拔由 scripts/build_geo_elevation.py
 *  从同一数据集离线采样（z9 双线性），见 public/elevation/kg-geo-elev.json。 */
const demTilesUrl = () => `https://api.maptiler.com/tiles/terrain-rgb-v2/tiles.json?key=${MAPTILER_KEY}`;
const ELEVATION_URL = "/elevation/kg-geo-elev.json";

/** 海拔表的紧凑格式（见 scripts/build_geo_elevation.py）：id 升序差分 + 以 unit_m 为单位的海拔。 */
interface ElevationTable {
  v: number;
  unit_m: number;
  id_delta: number[];
  elev: number[];
}
function decodeElevations(t: ElevationTable): Map<number, number> {
  const out = new globalThis.Map<number, number>();
  let id = 0;
  for (let i = 0; i < t.id_delta.length; i++) {
    id += t.id_delta[i];
    out.set(id, t.elev[i] * t.unit_m);
  }
  return out;
}

/** 远处的天空与大气透视，颜色跟随主题（宣纸底色 / 深色墨底）。 */
const skyFor = (isDark: boolean): SkySpecification =>
  isDark
    ? { "sky-color": "#1c2330", "horizon-color": "#3a3328", "fog-color": "#2a2620", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.35, "atmosphere-blend": 0.6 }
    : { "sky-color": "#b9d3ea", "horizon-color": "#f1ebdf", "fog-color": "#efe8da", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.55, "fog-ground-blend": 0.3, "atmosphere-blend": 0.7 };

/** deck.gl 以交错模式（interleaved）挂进 MapLibre：与地形共用深度缓冲与相机。
 *  2026-10-17 实测（spike）：非交错模式开地形后点最多偏 20px、且永远浮在山上；交错模式
 *  + 点带上真实海拔的 z，偏移 ≤1.4px。 */
function DeckOverlay(props: MapLibreOverlayProps) {
  const overlay = useControl(() => new MapLibreOverlay({ ...props, interleaved: true }));
  useEffect(() => {
    overlay.setProps(props);
    // 开发环境挂到 window 上，供贴地精度的自动化校验（比对 deck 投影与 map.project）。
    if (import.meta.env.DEV) (window as unknown as { __fojinMapOverlay?: unknown }).__fojinMapOverlay = overlay;
  }, [overlay, props]);
  return null;
}

/** MapTiler Streets with Chinese labels — one basemap per theme.
 *  The map canvas covers ~65% of the viewport, so a light basemap under the dark
 *  chrome was the single brightest thing left in dark mode. streets-v2-dark is a
 *  drop-in: it carries the SAME layer structure as streets-v2 (32 symbol layers,
 *  25 of them name-based), so the zh-label / Taiwan-name patching below applies
 *  unchanged. (dataviz-dark and basic-v2-dark are darker still but ship only
 *  11 / 7 label layers — far fewer place names.) */
const MAPTILER_KEY = "sBS5GCqJuftwymqkp64I";
const mapStyleUrl = (isDark: boolean, satellite: boolean) =>
  satellite
    // 卫星混合底图（影像 + 中文路名地名），只有一种配色，深浅主题共用。
    ? `https://api.maptiler.com/maps/hybrid/style.json?key=${MAPTILER_KEY}&language=zh`
    : `https://api.maptiler.com/maps/streets-v2${isDark ? "-dark" : ""}/style.json?key=${MAPTILER_KEY}&language=zh`;

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
  const isDark = useEffectiveTheme() === "dark";
  // useMemo 而非直接调用：typeColors() 每次返回新对象，直接进下面 layers 的
  // 依赖数组会让图层每帧重建；按 isDark 固定引用后既能随主题重算又不抖动。
  const TYPE_COLORS = useMemo(() => typeColors(isDark), [isDark]);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [arcTooltip, setArcTooltip] = useState<ArcTooltipState | null>(null);
  const mapRef = useRef<MapRef>(null);
  // 地图自己持有相机（非受控）；这里只跟踪 UI 需要的 zoom / bearing。
  const [camera, setCamera] = useState({ zoom: INITIAL_VIEW_STATE.zoom, bearing: 0 });
  const handleMove = useCallback((e: ViewStateChangeEvent) => {
    const { zoom, bearing } = e.viewState;
    setCamera((prev) => (prev.zoom === zoom && prev.bearing === bearing ? prev : { zoom, bearing }));
  }, []);
  // 2D / 3D：3D 打开地形、山体阴影、天空，点与弧线落在各自的真实海拔上。
  // 平面模式下关掉拖拽旋转——否则右键一拖就意外斜过去，又没有回正的入口。
  const [is3D, setIs3D] = useState(false);
  const [satellite, setSatellite] = useState(false);
  const setViewMode = useCallback((next: boolean) => {
    setIs3D(next);
    if (!next) setSatellite(false);
    if (typeof umami !== "undefined") umami.track("map_view_mode", { mode: next ? "3d" : "2d" });
  }, []);
  const resetNorth = useCallback(() => {
    mapRef.current?.easeTo({ bearing: 0, duration: VIEW_TRANSITION_MS / 2 });
  }, []);

  // 海拔表：第一次进 3D 才拉（gzip 约 250 KB），之后常驻。
  const [elevations, setElevations] = useState<ReadonlyMap<number, number> | null>(null);
  const [elevationError, setElevationError] = useState(false);
  useEffect(() => {
    if (!is3D || elevations || elevationError) return;
    let cancelled = false;
    fetch(ELEVATION_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<ElevationTable>;
      })
      .then((data) => { if (!cancelled) setElevations(decodeElevations(data)); })
      .catch((e) => {
        console.warn("[map] elevation table unavailable, 3D falls back to flat", e);
        if (!cancelled) setElevationError(true);
      });
    return () => { cancelled = true; };
  }, [is3D, elevations, elevationError]);
  // 地形只在海拔表就绪后才打开：先开地形、点还在 z=0 的话，高原上的点会整片埋进山里。
  // 海拔表拿不到时退化为「只倾斜、不起伏」，点照样在地图平面上，数据不会画错。
  const terrainOn = is3D && elevations !== null;

  // 镜头随模式过渡。放在 effect 里而不是点击回调：地形打开那一刻（海拔表到达）相机才该开始抬。
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({
      pitch: is3D ? PITCH_3D : 0,
      bearing: is3D ? BEARING_3D : 0,
      duration: VIEW_TRANSITION_MS,
    });
  }, [is3D]);

  /** 某个实体的 z（米，已乘夸张系数）。表里没有的（海拔表生成之后新增的实体）当场向
   *  地图查询；地形瓦片还没到时查不到，就先贴在 0，下一次 idle 再补。 */
  const [lateElevations, setLateElevations] = useState<ReadonlyMap<number, number>>(() => new globalThis.Map());
  const elevationOf = useCallback(
    (id: number) => {
      if (!terrainOn || !elevations) return 0;
      const known = elevations.get(id) ?? lateElevations.get(id);
      return (known ?? 0) * TERRAIN_EXAGGERATION;
    },
    [terrainOn, elevations, lateElevations],
  );
  const isPhone = useNarrowViewport(PHONE_QUERY);
  // A boolean, not the raw zoom, so the layers below rebuild only when the
  // threshold is crossed — not on every frame of a pinch.
  const denseOverview = isPhone && camera.zoom < DENSE_ZOOM;

  // Fly to focused entity when it changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focusEntity || focusEntity.longitude == null || focusEntity.latitude == null) return;
    map.flyTo({
      center: [focusEntity.longitude, focusEntity.latitude],
      zoom: Math.max(map.getZoom(), 9),
      duration: 1200,
    });
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
  const [firstSymbolId, setFirstSymbolId] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    fetch(mapStyleUrl(isDark, satellite))
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
        // 换底图（卫星 / 主题）会整体重建样式。地形若还开着，MapLibre 会在新样式的着色器
        // 就绪前画地形深度，抛 `shaderPreludeCode` of undefined（2026-10-17 本地复现）。
        // 先关地形，新样式 style.load 后由上面的 effect 重新挂上。
        const liveMap = mapRef.current?.getMap();
        if (liveMap?.getTerrain()) liveMap.setTerrain(null);
        setPatchedStyle(style as unknown as StyleSpecification);
        // 山体阴影插在第一个文字图层之下：阴影压住地面与道路，但不压地名。
        setFirstSymbolId(style.layers.find((l) => l.type === "symbol")?.id);
      })
      .catch((e) => {
        console.error("[style fetch err]", e);
      });
    return () => {
      cancelled = true;
    };
  }, [isDark, satellite]);

  // 地形命令式开关。不用 <Map terrain> 声明式属性：它在 DEM 源还没挂上时就调 setTerrain，
  // 失败后不重试——2026-10-17 本地实测地形一直是平的（queryTerrainElevation 恒为 0），
  // 而点已抬到真实海拔，于是全体悬空（拉萨 z11 偏 160px）。换主题 / 换卫星底图会整体
  // 重建样式、清掉源与地形，所以每次 style.load 后再挂一次。
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const apply = () => {
      if (!terrainOn) {
        if (map.getTerrain()) map.setTerrain(null);
        return;
      }
      if (!map.getSource(DEM_SOURCE_ID)) {
        map.addSource(DEM_SOURCE_ID, { type: "raster-dem", url: demTilesUrl(), tileSize: 512 });
      }
      map.setTerrain({ source: DEM_SOURCE_ID, exaggeration: TERRAIN_EXAGGERATION });
    };
    // 不用 isStyleLoaded() 判断：它要等所有瓦片都到齐才为真，平移中会一直是 false，
    // 而 style.load 早已发过，地形就永远挂不上。样式本身没加载完时 addSource 会抛错，
    // 那就等下一次 style.load。
    try {
      apply();
    } catch {
      /* style not ready yet — the style.load listener below will apply it */
    }
    map.on("style.load", apply);
    return () => {
      map.off("style.load", apply);
    };
  }, [terrainOn, patchedStyle]);

  const filteredEntities = useMemo(() => {
    return geoEntities.filter((e) => {
      if (!entityTypeFilter.includes(e.entity_type)) return false;
      if (currentYear !== null) {
        // Entities without year data are always shown (timeless features).
        // Only filter entities that explicitly fall outside the current year.
        // `!= null` (not `!== null`): /kg/geo omits null fields, so a missing
        // year arrives as undefined.
        if (e.year_start != null || e.year_end != null) {
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

  // 海拔表里没有的实体（表生成之后新增的）：地形瓦片到齐后（idle）向地图补查一次。
  // queryTerrainElevation 返回的值已乘夸张系数，存的是原始海拔。
  const handleIdle = useCallback(() => {
    const map = mapRef.current;
    if (!map || !terrainOn || !elevations) return;
    const found: Array<[number, number]> = [];
    for (const e of filteredEntities) {
      if (found.length >= 2000) break;
      if (elevations.has(e.id) || lateElevations.has(e.id)) continue;
      const q = map.queryTerrainElevation([e.longitude, e.latitude]);
      if (q == null) continue;
      found.push([e.id, Math.max(0, q / TERRAIN_EXAGGERATION)]);
    }
    if (found.length > 0) setLateElevations((prev) => new globalThis.Map([...prev, ...found]));
  }, [terrainOn, elevations, filteredEntities, lateElevations]);

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
        getPosition: (d) => [d.longitude, d.latitude, elevationOf(d.id)],
        getFillColor: (d) => {
          const c = TYPE_COLORS[d.entity_type] ?? [128, 128, 128];
          return [c[0], c[1], c[2], 200];
        },
        getLineColor: [255, 255, 255, 220],
        lineWidthMinPixels: 0.5,
        stroked: true,
        getRadius: 2500,
        radiusMinPixels: denseOverview ? 2 : 3,
        radiusMaxPixels: 9,
        // 斜视时贴地的圆会被压成扁椭圆、远处挤成一条线；立起来正对镜头。
        // 只影响点的朝向，锚点仍是它的经纬度与海拔。
        billboard: is3D,
        // 交错模式下点与地形共用深度缓冲：起伏的山体会把贴地的圆切掉一块（spike 实测
        // 40 个视角里 18 个可见 <80%）。标注是数据，不该被山挡住，一律画在最上层。
        parameters: { depthCompare: "always" },
        updateTriggers: { getPosition: [elevationOf] },
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
          getPosition: (d) => [d.longitude, d.latitude, elevationOf(d.id)],
          getFillColor: [255, 69, 0, 40],
          getLineColor: [255, 69, 0, Math.round(120 + 80 * (pulseScale - 1))],
          stroked: true,
          lineWidthMinPixels: 2.5,
          getRadius: 8000,
          radiusScale: pulseScale,
          radiusMinPixels: Math.round(12 * pulseScale),
          radiusMaxPixels: Math.round(22 * pulseScale),
          billboard: is3D,
          parameters: { depthCompare: "always" },
          pickable: false,
          updateTriggers: {
            getPosition: [elevationOf],
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
          // 两端是师、徒两个实体，与散点用同一张海拔表：弧线正好从点上升起、落回点上。
          getSourcePosition: (d) => [d.teacher_lng, d.teacher_lat, elevationOf(d.teacher_id)],
          getTargetPosition: (d) => [d.student_lng, d.student_lat, elevationOf(d.student_id)],
          updateTriggers: { getSourcePosition: [elevationOf], getTargetPosition: [elevationOf] },
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
  }, [filteredEntities, filteredArcs, showArcs, handleHover, handleClick, focusEntity, pulseScale, TYPE_COLORS, denseOverview, is3D, elevationOf]);

  return (
    <>
      {patchedStyle && (
        <Map
          ref={mapRef}
          initialViewState={INITIAL_VIEW_STATE}
          onMove={handleMove}
          onIdle={handleIdle}
          mapStyle={patchedStyle}
          onLoad={(e) => {
            collapseAttributionIfNarrow(e.target);
            if (import.meta.env.DEV) (window as unknown as { __fojinMap?: unknown }).__fojinMap = e.target;
          }}
          style={{ position: "absolute", inset: 0 }}
          // 平面模式不许旋转、倾斜（防误触且没有回正入口）；3D 才放开。
          dragRotate={is3D}
          touchPitch={is3D}
          maxPitch={is3D ? MAX_PITCH_3D : 60}
          sky={is3D ? skyFor(isDark) : undefined}
        >
          {terrainOn && (
            <>
              {/* 地形的 DEM 源在 effect 里命令式挂（见上）；山体阴影单独一个源——MapLibre 不建议
                  二者共用同一个源（会互相抢瓦片分辨率）。 */}
              {!satellite && (
                <Source id={HILLSHADE_SOURCE_ID} type="raster-dem" url={demTilesUrl()} tileSize={512}>
                  <Layer
                    id="fojin-hillshade"
                    type="hillshade"
                    beforeId={firstSymbolId}
                    paint={{
                      "hillshade-exaggeration": isDark ? 0.45 : 0.4,
                      "hillshade-shadow-color": isDark ? "#000000" : "#5c4f3d",
                      "hillshade-highlight-color": isDark ? "#7a6c55" : "#ffffff",
                      "hillshade-accent-color": isDark ? "#1a1612" : "#3d3326",
                      "hillshade-illumination-direction": 315,
                    }}
                  />
                </Source>
              )}
            </>
          )}
          <DeckOverlay
            layers={layers}
            // Smaller dots on phones must not mean harder taps: let a fingertip
            // within 8px pick the nearest dot. Desktop keeps exact mouse picking.
            pickingRadius={isPhone ? 8 : 0}
          />
        </Map>
      )}

      <div className="kg-map-view-controls">
        {/* 指北针放在切换钮之上：容器贴底排列，它出现/消失时切换钮不挪位，
            否则刚点完「3D」光标下就换成了指北针。 */}
        {is3D && (
          <Tooltip title={t("geo.reset_north")} placement="left">
            <button type="button" className="kg-map-compass" aria-label={t("geo.reset_north")} onClick={resetNorth}>
              {/* 指针跟着地图转：bearing 是地图相对正北的旋转，指针反向转回去仍指北。 */}
              <svg viewBox="0 0 24 24" width="18" height="18" style={{ transform: `rotate(${-camera.bearing}deg)` }} aria-hidden>
                <path d="M12 3 L15.5 12 L12 10.6 L8.5 12 Z" fill="var(--fj-cinnabar, #b5452c)" />
                <path d="M12 21 L8.5 12 L12 13.4 L15.5 12 Z" fill="currentColor" opacity="0.45" />
              </svg>
            </button>
          </Tooltip>
        )}
        {is3D && (
          <div className="kg-map-view-toggle" role="group" aria-label={t("geo.basemap")}>
            <button type="button" aria-pressed={!satellite} className={!satellite ? "is-active" : undefined} onClick={() => setSatellite(false)}>
              {t("geo.basemap_terrain")}
            </button>
            <button type="button" aria-pressed={satellite} className={satellite ? "is-active" : undefined} onClick={() => setSatellite(true)}>
              {t("geo.basemap_satellite")}
            </button>
          </div>
        )}
        <div className="kg-map-view-toggle" role="group" aria-label={t("geo.view_mode")}>
          <Tooltip title={t("geo.view_2d_tooltip")} placement="left">
            <button type="button" aria-pressed={!is3D} className={!is3D ? "is-active" : undefined} onClick={() => is3D && setViewMode(false)}>
              2D
            </button>
          </Tooltip>
          <Tooltip title={t("geo.view_3d_tooltip")} placement="left">
            <button type="button" aria-pressed={is3D} className={is3D ? "is-active" : undefined} onClick={() => !is3D && setViewMode(true)}>
              3D
            </button>
          </Tooltip>
        </div>
      </div>

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
            {(e.year_start != null || e.year_end != null) && (
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

// start/end may be undefined: /kg/geo omits null fields from its payload.
function formatYearRange(
  t: TFunction,
  start?: number | null,
  end?: number | null,
): string {
  if (start != null && end != null) return `${formatYear(t, start)} — ${formatYear(t, end)}`;
  if (start != null) return `${formatYear(t, start)} —`;
  if (end != null) return `— ${formatYear(t, end)}`;
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

// desc/nameEn may be undefined: /kg/geo omits null fields from its payload.
function detectCountryFlag(
  desc: string | null | undefined,
  nameEn: string | null | undefined,
  nameZh: string,
): string {
  const haystack = `${desc ?? ""} ${nameEn ?? ""} ${nameZh}`;
  for (const key of Object.keys(COUNTRY_FLAGS)) {
    if (haystack.includes(key)) return COUNTRY_FLAGS[key];
  }
  return "🏛️";
}

function detectCountryName(
  desc: string | null | undefined,
  nameEn: string | null | undefined,
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

function detectSource(desc: string | null | undefined): string | null {
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
