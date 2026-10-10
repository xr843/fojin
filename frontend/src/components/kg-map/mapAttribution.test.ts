import { describe, expect, it } from "vitest";
import { collapseAttributionIfNarrow } from "./mapAttribution";

/** Minimal stand-in for the maplibre Map surface the helper touches. */
function fakeMap(canvasWidth: number) {
  const container = document.createElement("div");
  container.innerHTML =
    '<details open class="maplibregl-ctrl maplibregl-ctrl-attrib maplibregl-compact maplibregl-compact-show">' +
    '<summary class="maplibregl-ctrl-attrib-button"></summary><div class="maplibregl-ctrl-attrib-inner">© MapTiler</div></details>';
  const canvasContainer = { offsetWidth: canvasWidth } as HTMLElement;
  return {
    map: { getContainer: () => container, getCanvasContainer: () => canvasContainer },
    attrib: container.querySelector(".maplibregl-ctrl-attrib")!,
  };
}

describe("collapseAttributionIfNarrow", () => {
  it("collapses the expanded attribution to the ⓘ button on phone-width maps", () => {
    const { map, attrib } = fakeMap(352);
    collapseAttributionIfNarrow(map);
    expect(attrib.classList.contains("maplibregl-compact")).toBe(true);
    expect(attrib.classList.contains("maplibregl-compact-show")).toBe(false);
  });

  it("leaves the desktop attribution expanded", () => {
    const { map, attrib } = fakeMap(1342);
    collapseAttributionIfNarrow(map);
    expect(attrib.classList.contains("maplibregl-compact-show")).toBe(true);
  });
});
