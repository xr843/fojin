import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import DeckGLMap from "./DeckGLMap";
import type { KGGeoEntity } from "../../api/client";

// WebGL-free stand-ins: record what DeckGLMap hands to deck.gl instead of drawing.
const deckProps: Array<Record<string, unknown>> = [];
vi.mock("@deck.gl/react", () => ({
  default: (props: Record<string, unknown>) => {
    deckProps.push(props);
    return null;
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
vi.mock("react-map-gl/maplibre", () => ({ Map: () => null }));

const ENTITIES = [
  { id: 1, name_zh: "大慈恩寺", entity_type: "monastery", latitude: 34.2, longitude: 108.9 },
  { id: 2, name_zh: "玄奘", entity_type: "person", latitude: 34.3, longitude: 108.95 },
] as KGGeoEntity[];

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

function lastRender() {
  const props = deckProps[deckProps.length - 1];
  const layers = props.layers as Array<{ props: Record<string, unknown> }>;
  const dots = layers.filter((l) => String(l.props.id).startsWith("entities-"));
  return { pickingRadius: props.pickingRadius, minRadii: dots.map((l) => l.props.radiusMinPixels) };
}

describe("DeckGLMap dot density on phones", () => {
  const originalMatchMedia = window.matchMedia;
  beforeEach(() => {
    deckProps.length = 0;
    // The basemap style fetch is irrelevant here — keep it pending.
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  });
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    vi.unstubAllGlobals();
  });

  const renderMap = () =>
    render(
      <DeckGLMap
        geoEntities={ENTITIES}
        lineageArcs={[]}
        showArcs={false}
        currentYear={null}
        entityTypeFilter={["monastery", "person"]}
        onEntityClick={() => {}}
      />,
    );

  it("draws smaller dots at the overview zoom on a phone, with a finger-sized pick radius", () => {
    mockViewport(true);
    renderMap();
    expect(lastRender()).toEqual({ pickingRadius: 8, minRadii: [2, 2] });
  });

  it("keeps desktop dots and exact picking unchanged", () => {
    mockViewport(false);
    renderMap();
    expect(lastRender()).toEqual({ pickingRadius: 0, minRadii: [3, 3] });
  });
});
