# Dark Mode — Design Spec

**Date:** 2026-07-23
**Status:** Approved (design), pending implementation plan
**Branch:** `feat/dark-mode`

## Goal

Add a dark ("暗色/黑夜") mode to fojin (https://fojin.app). The site is a Buddhist
digital-text platform whose visual identity is a warm paper-and-ink aesthetic anchored
on a maroon primary (`#8b2500`).

## Hard constraints (from the user)

1. **Dark mode must harmonize with the maroon primary `#8b2500`.** The maroon is the
   brand; dark mode must preserve it, not replace it.
2. **Dark mode must not hurt reading or usability.** This is a long-form scripture
   reading site — legibility of body text is paramount. Every color choice is checked
   against WCAG contrast.

## Decisions (agreed with user)

- **Trigger:** three-state control — `light | dark | system` — defaulting to `system`
  (follows OS `prefers-color-scheme`), with manual lock. Mirrors ChatGPT / Claude.ai.
- **Persistence:** `localStorage` (works for anonymous + logged-in users). Account-level
  sync is out of scope (YAGNI; can be added later).
- **Rollout:** foundation first, then a full sweep; **the toggle ships only once every
  page is consistent** — no page should flash blindingly white after switching to dark.
- **Palette:** warm dark ("暖墨黑"), NOT cold gray or pure black — preserves the ink-on-paper
  character and is easiest on the eyes for long reading.
- **Dark accent:** **B — 朱红 `#d9693c`** (a lightened, same-family variant of the maroon).

## Color system

fojin already exposes a semantic CSS-variable set in `src/styles/global.css` `:root`
(`--fj-*`, used in **471** places across the app). Dark mode is primarily a redefinition
of these tokens under a dark selector.

### The maroon-on-dark problem (why the accent must lighten)

`#8b2500` is itself dark (low luminance). Contrast measurements:

| Foreground | Background | Ratio | Verdict |
|---|---|---|---|
| `#8b2500` | `#f8f5ef` (light paper) | 8.2:1 | ✓ strong (current) |
| `#8b2500` | `#181410` (dark bg) | **2.1:1** | ✗ fails — nearly invisible |
| `#d9693c` (chosen) | `#181410` (dark bg) | **5.3:1** | ✓ passes incl. body text |

So the dark-mode accent is a lightened same-family variant, keeping brand identity while
restoring legibility.

### Token map (light → dark)

| Token | Light (current) | Dark (proposed) | Note |
|---|---|---|---|
| `--fj-bg` | `#f8f5ef` | `#181410` | warm ink-black |
| `--fj-bg-alt` | `#f0ebe2` | `#221d17` | |
| `--fj-ink` | `#2b2318` | `#ece4d6` | body text — 14.5:1 on `--fj-bg` |
| `--fj-ink-light` | `#5c4f3d` | `#c4b8a4` | |
| `--fj-ink-muted` | `#746958` | `#a99d89` | |
| `--fj-accent` | `#8b2500` | `#d9693c` | 5.3:1 on `--fj-bg` |
| `--fj-gold` | `#b08d57` | `#c9a86a` | |
| `--fj-border` | `#d9d0c1` | `#39312a` | |
| `--fj-card-bg` | `rgba(255,255,255,0.6)` | `#201b15` | solid in dark (translucent white reads wrong) |

The `<meta name="theme-color">` in `index.html` (`#8b2500`) flips to the dark bg
(`#181410`) in dark mode.

## Architecture — three layers

| Layer | Change | Coverage |
|---|---|---|
| **antd** | `ConfigProvider` in `src/App.tsx`: conditionally add `algorithm: theme.darkAlgorithm`; swap `colorPrimary` to `#d9693c` in dark. | All antd components flip at once. |
| **`--fj-*` variables** | Redefine the full token set under `:root[data-theme="dark"]` in `global.css`. | The 471 `var(--fj-*)` usages + every `var(--fj-*, #hex)` fallback flip automatically. |
| **Hardcoded-color sweep** | Convert bare hex in CSS / inline component styles to `--fj-*` vars (or add dark overrides). | The remaining manual work. |

### State & switching

- New **`src/stores/themeStore.ts`** (zustand, matching `authStore`/`timelineStore`):
  state `'light' | 'dark' | 'system'`, default `'system'`, persisted to `localStorage`.
- Subscribe to `window.matchMedia('(prefers-color-scheme: dark)')` so `system` mode
  tracks the OS live.
- The store writes `data-theme="light"|"dark"` onto `document.documentElement`.
- A three-state switch control in the app header (near the language / user menu).
- **FOUC prevention:** a tiny inline script in `index.html` `<head>` reads `localStorage`
  + `prefers-color-scheme` and sets `data-theme` on `<html>` before first paint, so a
  reload never flashes the wrong theme.

## Hardcoded-color inventory (honest breakdown)

Total bare-hex occurrences: **~560 in 19 CSS files** + **339 in 49 `.tsx/.ts` files**.
These are NOT all theme chrome. Classification:

- ✅ **Auto-flips** — the 471 `--fj-*` usages, antd components, and `var(--fj-*, #hex)`
  fallback patterns (e.g. `SharedQAPage.tsx` already uses `var(--fj-accent, #8b2500)`).
- 🔧 **Manual UI conversion** — bare hex in the 19 CSS files (top: `reader.css` 71,
  `kg.css` 66, `sources.css` 50, `collections`/`activity-feed` 44 each) + inline UI
  component colors (`EntityCard.tsx` ~30). Convert to `--fj-*` vars or add dark overrides.
- 📊 **Data-visualization theming (separate workstream)** — `ForceGraph.tsx`,
  `KGTimeline.tsx`, dashboard charts (`LanguageDonut.tsx`, `CategoryTreemap.tsx`),
  `ReaderParallelPanel.tsx`. These need dark backgrounds / axes / labels; categorical
  data hues are largely retained but re-checked for contrast on dark.
- 🔒 **Stay fixed (by decision)** — `ShareCard.tsx` (generates a fixed-brand share image,
  must not follow the UI theme) and `dynasty_years.ts` (dynasty colors are content data).

## Phasing (toggle ships only after P4)

- **P1 — Foundation:** `themeStore` + `data-theme` wiring + antd `darkAlgorithm` + `--fj-*`
  dark values + FOUC inline script + `theme-color` swap. Internally previewable.
- **P2 — CSS/UI sweep:** the 19 CSS files + inline UI component colors, page by page.
- **P3 — Data-viz:** dark adaptation of graphs / charts.
- **P4 — Full walkthrough:** every page in both themes; confirm no white flashes;
  **then** reveal the header toggle.

## Testing

- **Vitest:** `themeStore` logic — set/toggle, localStorage persistence, `system` live-follow
  of `prefers-color-scheme`, `data-theme` application.
- **Per-page walkthrough checklist:** every route in both light and dark.
- **Contrast checks** on the key reading surfaces (reader body, chat, links, buttons).

## Non-goals (YAGNI)

- Account-synced theme preference across devices.
- Per-page theme overrides.
- Theming the generated `ShareCard` image or content data colors (`dynasty_years`).

## Risks / watch-items

- **Data-viz contrast:** categorical palettes tuned for light backgrounds may lose
  separation on dark — needs a per-chart pass, not a blanket flip.
- **Sweep completeness:** a missed bare-hex on a low-traffic page = one white gash in
  dark mode. The P4 walkthrough is the guard; log any page deliberately deferred.
- **Third-party embeds** (if any) that render their own light chrome inside dark pages.
