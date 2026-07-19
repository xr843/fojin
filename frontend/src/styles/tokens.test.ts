import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, expect, it } from "vitest";

/**
 * The design-system text tokens must stay legible against the two surfaces they
 * are actually painted on: the warm page background (--fj-bg) and the white
 * card fill used by .coll-card / .source-card. WCAG 2.1 AA wants 4.5:1 for
 * normal-size body text, which is what every one of these tokens is used for.
 *
 * This is a token-level guard, not a per-page audit: --fj-ink-muted alone backs
 * the description text on /collections, /sources, /search and the KG sidebar,
 * so a regression here is a site-wide legibility regression.
 */

const CSS = readFileSync(resolve(__dirname, "global.css"), "utf-8");

function token(name: string): string {
  const m = CSS.match(new RegExp(`--${name}\\s*:\\s*(#[0-9a-fA-F]{3,8})`));
  if (!m) throw new Error(`token --${name} not found in global.css`);
  return m[1];
}

function srgbToLinear(c: number): number {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
  return (
    0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
  );
}

function contrast(fg: string, bg: string): number {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

const AA_NORMAL = 4.5;

describe("design token contrast", () => {
  const surfaces: Record<string, string> = {
    "page bg (--fj-bg)": token("fj-bg"),
    "card bg (#fff)": "#ffffff",
  };

  // Every token below is used as body-copy colour somewhere in the app.
  const textTokens = ["fj-ink", "fj-ink-light", "fj-ink-muted", "fj-accent"];

  for (const name of textTokens) {
    for (const [surfaceName, surface] of Object.entries(surfaces)) {
      it(`--${name} meets WCAG AA on ${surfaceName}`, () => {
        const ratio = contrast(token(name), surface);
        expect(
          ratio,
          `--${name} (${token(name)}) on ${surface} = ${ratio.toFixed(2)}:1, need >= ${AA_NORMAL}`,
        ).toBeGreaterThanOrEqual(AA_NORMAL);
      });
    }
  }

  it("keeps a visible three-step ink hierarchy", () => {
    const bg = token("fj-bg");
    const ink = contrast(token("fj-ink"), bg);
    const light = contrast(token("fj-ink-light"), bg);
    const muted = contrast(token("fj-ink-muted"), bg);
    // Darkening --fj-ink-muted to pass AA must not collapse it into --fj-ink-light.
    expect(ink).toBeGreaterThan(light);
    expect(light).toBeGreaterThan(muted);
  });
});
