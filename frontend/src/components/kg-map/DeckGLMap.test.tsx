import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import DeckGLMap from "./DeckGLMap";
import type { KGGeoEntity, KGLineageArc } from "../../api/client";

// WebGL-free stand-ins: record what DeckGLMap hands to the MapLibre map and to the
// interleaved deck.gl overlay instead of drawing.
const overlayProps: Array<Record<string, unknown>> = [];
const mapProps: Array<Record<string, unknown>> = [];
vi.mock("@deck.gl/maplibre", () => ({
  MapLibreOverlay: class {
    constructor(props: Record<string, unknown>) {
      overlayProps.push(props);
    }
    setProps(props: Record<string, unknown>) {
      overlayProps.push(props);
    }
  },
}));
vi.mock("@deck.gl/layers", () => {
  class FakeLayer {
    props: Record<string, unknown>;
    constructor(props: Record<string, unknown>) {
      this.props = props;
    }
  }
  return { ScatterplotLayer: FakeLayer, ArcLayer: FakeLayer };
});
vi.mock("react-map-gl/maplibre", () => ({
  Map: (props: Record<string, unknown> & { children?: ReactNode }) => {
    mapProps.push(props);
    return <div data-testid="map">{props.children}</div>;
  },
  Source: ({ children }: { children?: ReactNode }) => <>{children}</>,
  Layer: () => null,
  useControl: (factory: () => unknown) => factory(),
}));

const ENTITIES = [
  { id: 1, name_zh: "大慈恩寺", entity_type: "monastery", latitude: 34.2, longitude: 108.9 },
  { id: 2, name_zh: "玄奘", entity_type: "person", latitude: 34.3, longitude: 108.95 },
] as KGGeoEntity[];
// 紧凑格式：id 差分 [1, 1] → id 1、2；海拔 ×10 m
const ELEVATIONS = { v: 1, unit_m: 10, id_delta: [1, 1], elev: [42, 365] };
const ARCS = [
  { teacher_id: 2, teacher_name: "玄奘", teacher_lat: 34.3, teacher_lng: 108.95, student_id: 1, student_name: "窥基", student_lat: 34.2, student_lng: 108.9, year: null, school: null },
] as KGLineageArc[];

function mockViewport(phone: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: phone && query === "(max-width: 768px)",
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

/** 底图样式立即返回最小样式；海拔表按 URL 返回。 */
function stubFetch() {
  const fetchMock = vi.fn((url: string) => {
    const body = String(url).includes("kg-geo-elev") ? ELEVATIONS : { layers: [{ id: "label", type: "symbol", layout: {} }] };
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastLayers() {
  const props = overlayProps[overlayProps.length - 1];
  return props.layers as Array<{ props: Record<string, unknown> }>;
}

function lastRender() {
  const props = overlayProps[overlayProps.length - 1];
  const dots = lastLayers().filter((l) => String(l.props.id).startsWith("entities-"));
  return { pickingRadius: props.pickingRadius, minRadii: dots.map((l) => l.props.radiusMinPixels) };
}

const renderMap = (showArcs = false) =>
  render(
    <DeckGLMap
      geoEntities={ENTITIES}
      lineageArcs={showArcs ? ARCS : []}
      showArcs={showArcs}
      currentYear={null}
      entityTypeFilter={["monastery", "person"]}
      onEntityClick={() => {}}
    />,
  );

describe("DeckGLMap dot density on phones", () => {
  const originalMatchMedia = window.matchMedia;
  beforeEach(() => {
    overlayProps.length = 0;
    mapProps.length = 0;
    stubFetch();
  });
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    vi.unstubAllGlobals();
  });

  it("draws smaller dots at the overview zoom on a phone, with a finger-sized pick radius", async () => {
    mockViewport(true);
    renderMap();
    await waitFor(() => expect(overlayProps.length).toBeGreaterThan(0));
    expect(lastRender()).toEqual({ pickingRadius: 8, minRadii: [2, 2] });
  });

  it("keeps desktop dots and exact picking unchanged", async () => {
    mockViewport(false);
    renderMap();
    await waitFor(() => expect(overlayProps.length).toBeGreaterThan(0));
    expect(lastRender()).toEqual({ pickingRadius: 0, minRadii: [3, 3] });
  });
});

describe("DeckGLMap 2D / 3D view toggle", () => {
  const originalMatchMedia = window.matchMedia;
  beforeEach(() => {
    overlayProps.length = 0;
    mapProps.length = 0;
    mockViewport(false);
  });
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    vi.unstubAllGlobals();
  });

  function snapshot() {
    const map = mapProps[mapProps.length - 1];
    const layers = lastLayers();
    const dots = layers.filter((l) => String(l.props.id).startsWith("entities-"));
    const positions = dots.flatMap((l) =>
      (l.props.data as KGGeoEntity[]).map((d) => (l.props.getPosition as (e: KGGeoEntity) => number[])(d)),
    );
    const arc = layers.find((l) => l.props.id === "lineage-arcs");
    const arcEnds = arc
      ? (arc.props.data as KGLineageArc[]).map((d) => [
          (arc.props.getSourcePosition as (a: KGLineageArc) => number[])(d),
          (arc.props.getTargetPosition as (a: KGLineageArc) => number[])(d),
        ])
      : [];
    return {
      dragRotate: map.dragRotate,
      touchPitch: map.touchPitch,
      sky: map.sky,
      billboards: dots.map((l) => l.props.billboard),
      depth: dots.map((l) => (l.props.parameters as { depthCompare?: string } | undefined)?.depthCompare),
      positions,
      arcEnds,
    };
  }

  it("2D: flat, rotation off, every dot at sea level on its own lng/lat", async () => {
    const fetchMock = stubFetch();
    const { container } = renderMap(true);
    await waitFor(() => expect(overlayProps.length).toBeGreaterThan(0));
    const flat = snapshot();
    expect(flat).toMatchObject({ dragRotate: false, touchPitch: false, sky: undefined, billboards: [false, false] });
    expect(flat.positions).toEqual([[108.9, 34.2, 0], [108.95, 34.3, 0]]);
    expect(flat.arcEnds).toEqual([[[108.95, 34.3, 0], [108.9, 34.2, 0]]]);
    expect(container.querySelector(".kg-map-compass")).toBeNull();
    // 平面模式不拉海拔表
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("kg-geo-elev"))).toBe(false);
  });

  it("3D: dots and arc ends sit at their own elevation × the terrain exaggeration, never hidden by terrain", async () => {
    stubFetch();
    const { getByRole, container } = renderMap(true);
    await waitFor(() => expect(overlayProps.length).toBeGreaterThan(0));
    fireEvent.click(getByRole("button", { name: "3D" }));
    await waitFor(() => expect(snapshot().positions[0][2]).toBeGreaterThan(0));
    const tilted = snapshot();
    expect(tilted).toMatchObject({ dragRotate: true, touchPitch: true, billboards: [true, true], depth: ["always", "always"] });
    expect(tilted.sky).toBeTruthy();
    // 经纬度不变；z = 海拔表 × 1.6
    expect(tilted.positions).toEqual([[108.9, 34.2, 420 * 1.6], [108.95, 34.3, 3650 * 1.6]]);
    // 弧线两端与对应实体同高：从点上升起、落回点上
    expect(tilted.arcEnds).toEqual([[[108.95, 34.3, 3650 * 1.6], [108.9, 34.2, 420 * 1.6]]]);
    expect(container.querySelector(".kg-map-compass")).not.toBeNull();

    fireEvent.click(getByRole("button", { name: "2D" }));
    await waitFor(() => expect(snapshot().positions[1][2]).toBe(0));
    expect(snapshot()).toMatchObject({ dragRotate: false, touchPitch: false, billboards: [false, false] });
  });

  it("3D without an elevation table stays flat instead of drawing dots at the wrong height", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) =>
      String(url).includes("kg-geo-elev")
        ? Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) } as Response)
        : Promise.resolve({ ok: true, json: () => Promise.resolve({ layers: [] }) } as Response),
    ));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { getByRole } = renderMap();
    await waitFor(() => expect(overlayProps.length).toBeGreaterThan(0));
    fireEvent.click(getByRole("button", { name: "3D" }));
    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(snapshot().positions).toEqual([[108.9, 34.2, 0], [108.95, 34.3, 0]]);
    warn.mockRestore();
  });
});
