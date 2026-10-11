/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { dirname, resolve } from "path";
import { mkdirSync, writeFileSync, readFileSync } from "fs";
import { localizeShell, shellPlan } from "./src/seo/buildShells";

/**
 * 为关键路由生成独立 HTML 文件，让搜索引擎无需 JS 即可获取正确的
 * title / description / noscript 内容。Nginx/CDN 对 /sources 返回
 * dist/sources/index.html，爬虫直接拿到正确 meta。
 */
function seoPages(): Plugin {
  return {
    name: "seo-pages",
    closeBundle() {
      const distDir = resolve(__dirname, "dist");
      let template: string;
      try {
        template = readFileSync(resolve(distDir, "index.html"), "utf-8");
      } catch {
        return; // dist not ready
      }

      // One shell per (route × UI language); nginx picks the file by ?lang=.
      // See src/seo/buildShells.ts and frontend/nginx.conf (`map $arg_lang`).
      for (const entry of shellPlan(template)) {
        const out = resolve(distDir, entry.outFile);
        mkdirSync(dirname(out), { recursive: true });
        writeFileSync(out, localizeShell(template, entry));
      }
    },
  };
}

function manualChunks(id: string): string | undefined {
  if (
    [
      "/node_modules/react/",
      "/node_modules/react-dom/",
      "/node_modules/react-router-dom/",
    ].some((pkg) => id.includes(pkg))
  ) {
    return "vendor-react";
  }
  // antd 不再强制并入单一 vendor chunk：那样会把 admin 才用的 Table/Form 等
  // 和首页只需的 AutoComplete 焊在一起(~1.15MB),而首页(唯一静态导入的路由)
  // 一 import antd 就把整块拉进首屏。交回 rolldown 按已有的路由懒加载边界拆分,
  // 首屏只承担自己那一小片 antd,admin 的重组件留在各自 route chunk。
  if (id.includes("/node_modules/@tanstack/react-query/")) {
    return "vendor-query";
  }
  if (id.includes("/node_modules/d3/")) {
    return "vendor-d3";
  }
  if (id.includes("/src/utils/sourceUrls")) {
    return "source-urls";
  }
  return undefined;
}

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: false, // We provide our own manifest.json in public/
      workbox: {
        // Include webp so the real hero (landscape-bg.webp, ~19KB) is precached;
        // exclude landscape-bg.png (577KB) — it's only the og:image for social
        // crawlers, which don't run a service worker, so precaching it into every
        // PWA install just wastes ~577KB the user never sees.
        // og-image.png (236KB) is excluded for exactly the same reason: it is the
        // share card served to WeChat/Twitter crawlers, never rendered in the app.
        globPatterns: ["**/*.{js,css,html,ico,png,svg,webp}"],
        // The per-route / per-language crawler shells (src/seo/buildShells.ts) are
        // never used by the SW: every navigation is answered from the precached
        // root index.html (navigateFallback). Precaching ~100 of them would add
        // ~1.2 MB to every visitor's first load for nothing.
        globIgnores: ["**/landscape-bg.png", "**/og-image.png", "**/index.*.html", "*/**/index.html"],
        // /agents and /llms.txt are real files served outside the SPA, and a
        // navigation to either would otherwise be answered from the precached
        // index.html: /agents has no React Router route (→ 404 page for anyone
        // with the SW installed), and /llms.txt isn't in globPatterns at all so
        // it is never precached. Crawlers don't run a SW and so never saw this;
        // only returning humans would.
        // The `(\?|$)` is load-bearing: workbox tests these against
        // `pathname + search`, not pathname, so an anchored `/^\/agents$/`
        // stops matching the moment a link carries `?utm_source=…` — and the
        // navigation falls back to the SPA shell, which has no /agents route.
        // A shared link is exactly the case that carries query params.
        navigateFallbackDenylist: [
          /^\/api\//,
          /^\/agents(\?|$)/,
          /^\/llms\.txt(\?|$)/,
        ],
        skipWaiting: true,
        clientsClaim: true,
      },
    }),
    seoPages(),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    testTimeout: 10000,
    // React 19's scheduler runs on setImmediate under Node. When a render or
    // unmount lands late, `performWorkUntilDeadline` is still queued as vitest
    // destroys the file's jsdom environment; the callback then fires with
    // `window` already gone. Every test passes (251/251) but the run is marked
    // failed, measured at ~29% of full-suite runs — roughly one CI rerun in
    // three, for a race that happens strictly after the tests are done.
    //
    // Ignore that one signature and nothing else: all three conditions must
    // hold, so a genuine unhandled error — including any *other* ReferenceError,
    // or this same message from application code rather than React's scheduler —
    // still fails the run. Drop this once React/vitest stop racing at teardown.
    //
    // Not fixed in test code: draining the setImmediate queue in afterAll was
    // tried and measured (paired A/B, 14 pairs) — it did not help (baseline 4/14
    // vs 7/14 with the drain), so the config-level filter is the honest option.
    onUnhandledError(error) {
      const isTeardownRace =
        error.type === "Uncaught Exception" &&
        error.name === "ReferenceError" &&
        error.message === "window is not defined" &&
        (error.stack ?? "").includes("performWorkUntilDeadline");
      if (isTeardownRace) return false;
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/graphql": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
