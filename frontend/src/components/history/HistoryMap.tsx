import { useEffect, useMemo, useRef, useState } from "react";
import { Map, Source, Layer, type MapRef, type MapLayerMouseEvent } from "react-map-gl/maplibre";
import type { ExpressionSpecification, StyleSpecification } from "maplibre-gl";
import { patchZhLabels } from "../kg-map/zhMapStyle";
import "maplibre-gl/dist/maplibre-gl.css";

/**
 * 佛教史长卷旁边的地图（借鉴「江山时序」时间与地图联动）。只画有出处的点：
 * - 籍贯 / 葬地：DILA 人名库的 placeOfOrigin / placeOfBurial → DILA 地名库坐标；
 * - 导览各站：该站说明里写到的地点（historyTours.json 的 pl）。
 * 底图与 /map 同一个 MapTiler key（限 fojin.app 来源）。
 */

const MAPTILER_KEY = "sBS5GCqJuftwymqkp64I";
const styleUrl = (dark: boolean) =>
  dark
    ? `https://api.maptiler.com/maps/streets-v2-dark/style.json?key=${MAPTILER_KEY}&language=zh`
    : `https://api.maptiler.com/maps/landscape/style.json?key=${MAPTILER_KEY}&language=zh`;

export interface MapPoint {
  id: string;
  lon: number;
  lat: number;
  label: string;
  /** base：所有人的籍贯（淡）；alive：游标年份在世；focus：选中的人；related：师/弟子；burial：葬地；tour：导览站；current：当前站 */
  kind: "base" | "alive" | "focus" | "related" | "burial" | "tour" | "current";
  /** 导览站序（1 起） */
  n?: number;
  /** 点到哪个人 */
  person?: string;
}

export interface MapEdge {
  from: [number, number];
  to: [number, number];
  gap?: boolean;
}

const COLORS: Record<MapPoint["kind"], string> = {
  base: "#8a7a62",
  alive: "#8b2500",
  focus: "#b23a1a",
  related: "#b23a1a",
  burial: "#5c4f3d",
  tour: "#b23a1a",
  current: "#b23a1a",
};

const colorExpr: ExpressionSpecification = ["match", ["get", "kind"], ...Object.entries(COLORS).flat(), "#8b2500"] as unknown as ExpressionSpecification;

export default function HistoryMap({
  points,
  edges,
  focus,
  dark,
  traditional = false,
  onPick,
  attribution,
}: {
  points: MapPoint[];
  edges: MapEdge[];
  /** 镜头要看的点（单点飞过去，多点框住） */
  focus: Array<[number, number]>;
  dark: boolean;
  /** 繁体界面：底图地名优先用繁体 */
  traditional?: boolean;
  onPick: (personId: string) => void;
  attribution: string;
}) {
  const ref = useRef<MapRef>(null);
  // 底图地名改中文（MapTiler 的 language 参数对中文不生效，要改样式里的文字层，与 /map 共用同一补丁）
  const [style, setStyle] = useState<StyleSpecification | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(styleUrl(dark))
      .then((r) => r.json())
      .then((json) => {
        if (!cancelled) setStyle(patchZhLabels(json, traditional) as unknown as StyleSpecification);
      })
      .catch(() => {
        if (!cancelled) setStyle(null);
      });
    return () => {
      cancelled = true;
    };
  }, [dark, traditional]);

  const pointData = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: points.map((p) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
        properties: { id: p.id, label: p.label, kind: p.kind, n: p.n ?? 0, person: p.person ?? "" },
      })),
    }),
    [points],
  );
  const edgeData = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: edges.map((e, i) => ({
        type: "Feature" as const,
        geometry: { type: "LineString" as const, coordinates: [e.from, e.to] },
        properties: { i, gap: e.gap ? 1 : 0 },
      })),
    }),
    [edges],
  );

  // 镜头：一个点飞过去，多个点框住。地图要等底图样式取回、加载完才在；
  // 加载前到的镜头请求先记着，onLoad 时补上（11-27 实测：选中玄奘后地图停在全国视野不动）
  const focusRef = useRef(focus);
  useEffect(() => {
    focusRef.current = focus;
  });
  const applyFocus = (animate: boolean) => {
    const map = ref.current;
    const f = focusRef.current;
    if (!map || f.length === 0) return;
    const duration = animate ? 900 : 0;
    if (f.length === 1) {
      map.flyTo({ center: f[0], zoom: Math.max(map.getZoom(), 5.2), duration });
      return;
    }
    const lons = f.map((x) => x[0]);
    const lats = f.map((x) => x[1]);
    map.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 56, maxZoom: 6.5, duration },
    );
  };
  const focusKey = focus.map((f) => f.join(",")).join(";");
  useEffect(() => {
    applyFocus(true);
    // focusKey 足以代表 focus 的变化；applyFocus 读 ref
  }, [focusKey]);

  const onClick = (e: MapLayerMouseEvent) => {
    const f = e.features?.[0];
    const person = f?.properties?.person as string | undefined;
    if (person) onPick(person);
  };

  if (!style) return null;
  return (
    <Map
      ref={ref}
      initialViewState={{ longitude: 112, latitude: 32, zoom: 3.6 }}
      mapStyle={style}
      localIdeographFontFamily="'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif"
      interactiveLayerIds={["hm-points", "hm-tour"]}
      onClick={onClick}
      onLoad={() => applyFocus(false)}
      cursor="default"
      attributionControl={{ compact: true, customAttribution: attribution }}
      style={{ width: "100%", height: "100%" }}
      dragRotate={false}
      pitchWithRotate={false}
    >
      <Source id="hm-edges" type="geojson" data={edgeData}>
        <Layer
          id="hm-edges-solid"
          type="line"
          filter={["==", ["get", "gap"], 0]}
          paint={{ "line-color": COLORS.tour, "line-width": 2, "line-opacity": 0.75 }}
          layout={{ "line-cap": "round" }}
        />
        <Layer
          id="hm-edges-gap"
          type="line"
          filter={["==", ["get", "gap"], 1]}
          paint={{ "line-color": COLORS.tour, "line-width": 2, "line-opacity": 0.6, "line-dasharray": [2, 2] }}
        />
      </Source>
      <Source id="hm-pts" type="geojson" data={pointData}>
        <Layer
          id="hm-points"
          type="circle"
          filter={["!", ["in", ["get", "kind"], ["literal", ["tour", "current"]]]]}
          paint={{
            "circle-color": colorExpr,
            "circle-radius": ["match", ["get", "kind"], "base", 2.6, "focus", 7, "related", 5, "burial", 5, 5],
            "circle-opacity": ["match", ["get", "kind"], "base", 0.45, 0.9],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": ["match", ["get", "kind"], "base", 0, 1.2],
          }}
        />
        <Layer
          id="hm-tour"
          type="circle"
          filter={["in", ["get", "kind"], ["literal", ["tour", "current"]]]}
          paint={{
            "circle-color": colorExpr,
            "circle-radius": ["match", ["get", "kind"], "current", 11, 8],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.5,
          }}
        />
        <Layer
          id="hm-tour-n"
          type="symbol"
          filter={["in", ["get", "kind"], ["literal", ["tour", "current"]]]}
          layout={{ "text-field": ["to-string", ["get", "n"]], "text-size": 10, "text-allow-overlap": true, "text-font": ["Noto Sans Regular"] }}
          paint={{ "text-color": "#ffffff" }}
        />
        <Layer
          id="hm-labels"
          type="symbol"
          filter={["!=", ["get", "kind"], "base"]}
          layout={{
            "text-field": ["get", "label"],
            "text-size": ["match", ["get", "kind"], "current", 14, "focus", 14, 12],
            "text-offset": [0, 1.1],
            "text-anchor": "top",
            "text-max-width": 10,
            "text-font": ["Noto Sans Regular"],
          }}
          paint={{
            "text-color": dark ? "#f2e8d8" : "#2b2318",
            "text-halo-color": dark ? "#1a1612" : "#fbf7ef",
            "text-halo-width": 1.6,
          }}
        />
      </Source>
    </Map>
  );
}
