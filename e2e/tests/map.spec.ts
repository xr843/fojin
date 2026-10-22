import { test, expect } from "@playwright/test";
import { PNG } from "pngjs";

/**
 * /map (佛教地理) — the route that CI structurally cannot protect.
 *
 * Encodes the 2026-09-22 incident (#1239, reverted in #1249): bumping
 * maplibre-gl 5.22→6.8 shipped green through every gate and took the page down.
 * The post-mortem found TWO independent breakages, and they fail differently:
 *
 *  1. react-map-gl ≤8.1.2 reads maplibre's internal `map.transform`, which
 *     maplibre 6 changed → `_updateSize` throws → the whole route falls into
 *     RouteErrorBoundary. LOUD: no canvas at all.
 *  2. maplibre 6 fetches its worker as a separate ESM module at runtime; vite
 *     never emitted it → 404 → no tile/geojson parsing. SILENT: the canvas is
 *     there and the background colour paints, but nothing is ever drawn on it.
 *
 * Why the obvious assertions do not work:
 *  - `canvas` alone misses (2) entirely.
 *  - `canvas` *first()* is deck.gl's transparent overlay, not maplibre's — it
 *    keeps rendering its own markers even when maplibre is dead, so asserting on
 *    it misses (2) too. Hence the explicit `.maplibregl-canvas` selector.
 *  - `gl.readPixels` returns all zeros on maplibre's context (no
 *    `preserveDrawingBuffer`), so pixels must come from a screenshot, which
 *    captures the composited frame.
 *
 * So there are two independent assertions. *Colour diversity* on maplibre's own
 * canvas: a real basemap has thousands of distinct colours, a dead worker leaves
 * a flat wash of one or two (measured on production, maplibre 5 healthy:
 * **19,050** distinct — the threshold below has a ~380× margin). And a network
 * check for a failed worker fetch, which holds even when MapTiler is slow or
 * down and is the assertion that pins breakage (2) directly.
 */
const MIN_DISTINCT_COLOURS = 50;

test("map basemap actually renders and the route does not crash", async ({ page }) => {
  const crashes: string[] = [];
  const deadWorker: string[] = [];
  page.on("pageerror", (err) => crashes.push(String(err)));
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (text.includes("cloudflareinsights")) return; // CSP-rejected RUM beacon, known noise
    if (/RouteErrorBoundary|maplibre|_updateSize|worker/i.test(text)) crashes.push(text);
  });
  // Breakage (2) leaves a fingerprint in the network log before it shows up in
  // pixels: maplibre asks for its worker and the server has no such file. This
  // assertion is the one that does not depend on the basemap rendering at all,
  // so it still holds when MapTiler is slow, rate-limiting, or down. On
  // maplibre 5 no such request is ever made (the worker is an inlined blob), so
  // it is simply vacuous there rather than wrong.
  page.on("requestfailed", (r) => {
    if (/maplibre-gl-worker/.test(r.url())) deadWorker.push(`FAILED ${r.url()} :: ${r.failure()?.errorText}`);
  });
  page.on("response", (r) => {
    if (/maplibre-gl-worker/.test(r.url()) && r.status() >= 400) deadWorker.push(`${r.status()} ${r.url()}`);
  });

  await page.goto("/map");

  // Breakage (1) shows up here: the route crashed, so no map canvas was mounted.
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible({ timeout: 30_000 });

  // Breakage (2) shows up here: canvas present, but nothing was ever drawn on it.
  await expect
    .poll(
      async () => {
        const shot = await canvas.screenshot();
        const png = PNG.sync.read(shot);
        const seen = new Set<number>();
        // Sample every 4th pixel — enough to tell "flat wash" from "real map",
        // and keeps a 1182×679 frame well under a second.
        for (let i = 0; i < png.data.length; i += 16) {
          seen.add((png.data[i] << 16) | (png.data[i + 1] << 8) | png.data[i + 2]);
          if (seen.size > MIN_DISTINCT_COLOURS) break;
        }
        return seen.size;
      },
      {
        timeout: 40_000,
        message:
          "maplibre canvas stayed a flat wash — basemap tiles never rendered " +
          "(worker dead?), even though the canvas element exists",
      },
    )
    .toBeGreaterThan(MIN_DISTINCT_COLOURS);

  expect(deadWorker, `maplibre worker never loaded:\n${deadWorker.join("\n")}`).toHaveLength(0);
  expect(crashes, `map route errors:\n${crashes.join("\n")}`).toHaveLength(0);
});
