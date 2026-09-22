import { test, expect } from "@playwright/test";

/**
 * /map (佛教地理) — the route that CI structurally cannot protect.
 *
 * Encodes the 2026-09-22 incident: bumping maplibre-gl 5.22→6.8 (#1239) shipped
 * green through every gate and took the whole page down. maplibre 6 loads its
 * worker as a separate ESM module fetched at runtime (`maplibre-gl-worker.mjs`);
 * vite never emitted that file, so it 404'd, the map failed to initialise, and
 * `_updateSize` threw on undefined — the entire route fell into
 * RouteErrorBoundary. Reverted in #1249.
 *
 * Why no existing gate caught it: `vite build` succeeds because the worker is
 * fetched by URL at *runtime*, and this smoke suite covered `/`, `/search`,
 * `/chat` and `/login` — never `/map`. A WebGL route can only be verified by
 * actually rendering it.
 *
 * Hence the assertion is on painted pixels, not on the canvas element: a
 * maplibre failure still leaves a zero-sized or blank canvas in the DOM, so
 * `toBeVisible()` alone would have passed through this very incident.
 */
test("map renders actual pixels and does not crash the route", async ({ page }) => {
  const crashes: string[] = [];
  page.on("pageerror", (err) => crashes.push(String(err)));
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (text.includes("cloudflareinsights")) return; // CSP-rejected RUM beacon, known noise
    // The incident's signature: the route's own error boundary catching a throw.
    if (/RouteErrorBoundary|maplibre|_updateSize/i.test(text)) crashes.push(text);
  });

  await page.goto("/map");

  const canvas = page.locator("canvas").first();
  await expect(canvas).toBeVisible({ timeout: 30_000 });

  // Poll until the GL context has painted something. Tiles arrive over the
  // network, so a single immediate read races the first frame.
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const c = document.querySelector("canvas") as HTMLCanvasElement | null;
          if (!c || !c.width || !c.height) return "no-canvas";
          const gl = (c.getContext("webgl2") || c.getContext("webgl")) as WebGLRenderingContext | null;
          if (!gl) return "no-webgl-context";
          const px = new Uint8Array(4 * 100);
          gl.readPixels(
            Math.floor(c.width / 2) - 5,
            Math.floor(c.height / 2) - 5,
            10,
            10,
            gl.RGBA,
            gl.UNSIGNED_BYTE,
            px,
          );
          return px.some((v) => v !== 0) ? "painted" : "blank";
        }),
      { timeout: 30_000, message: "map canvas never painted any pixels" },
    )
    .toBe("painted");

  expect(crashes, `map route errors:\n${crashes.join("\n")}`).toHaveLength(0);
});
