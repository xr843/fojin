/** maplibre's AttributionControl threshold for "narrow" maps (canvas ≤ 640px). */
const NARROW_MAP_PX = 640;

interface AttributionHost {
  getContainer(): HTMLElement;
  getCanvasContainer(): HTMLElement;
}

/**
 * Start the attribution collapsed (just the ⓘ button) on phone-width maps.
 *
 * maplibre renders a compact attribution EXPANDED and only folds it on the map's
 * own `drag` event. Under <DeckGL> the deck controller owns every gesture, so
 * maplibre never sees a drag and the two-line credit sat over the bottom of a
 * 352px-wide map forever. This is exactly what maplibre's _updateCompactMinimize
 * does on drag (drop `maplibregl-compact-show`); tapping ⓘ re-expands it through
 * maplibre's own toggle, so the credit stays one tap away.
 */
export function collapseAttributionIfNarrow(map: AttributionHost): void {
  if (map.getCanvasContainer().offsetWidth > NARROW_MAP_PX) return;
  map
    .getContainer()
    .querySelector(".maplibregl-ctrl-attrib.maplibregl-compact")
    ?.classList.remove("maplibregl-compact-show");
}
