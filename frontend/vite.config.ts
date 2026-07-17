/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { resolve } from "path";
import { mkdirSync, writeFileSync, readFileSync } from "fs";
import { STATIC_SEO_PAGES } from "./src/seo/staticPages";

/**
 * 为关键路由生成独立 HTML 文件，让搜索引擎无需 JS 即可获取正确的
 * title / description / noscript 内容。Nginx/CDN 对 /sources 返回
 * dist/sources/index.html，爬虫直接拿到正确 meta。
 */
function seoPages(): Plugin {
  const pages = STATIC_SEO_PAGES;

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

      for (const [route, meta] of Object.entries(pages)) {
        let html = template;

        // Replace title
        html = html.replace(
          /<title>[^<]*<\/title>/,
          `<title>${meta.title}</title>`,
        );

        // Replace meta description
        html = html.replace(
          /<meta name="description" content="[^"]*"/,
          `<meta name="description" content="${meta.desc}"`,
        );

        // Replace canonical
        html = html.replace(
          /<link rel="canonical" href="[^"]*"/,
          `<link rel="canonical" href="https://fojin.app/${route}"`,
        );

        // Replace og:url
        html = html.replace(
          /<meta property="og:url" content="[^"]*"/,
          `<meta property="og:url" content="https://fojin.app/${route}"`,
        );

        // Replace og:title
        html = html.replace(
          /<meta property="og:title" content="[^"]*"/,
          `<meta property="og:title" content="${meta.title}"`,
        );

        // Replace og:description
        html = html.replace(
          /<meta property="og:description" content="[^"]*"/,
          `<meta property="og:description" content="${meta.desc}"`,
        );

        // Replace Twitter metadata as well; otherwise route pages inherit the
        // generic SPA shell description.
        html = html.replace(
          /<meta name="twitter:title" content="[^"]*"/,
          `<meta name="twitter:title" content="${meta.title}"`,
        );
        html = html.replace(
          /<meta name="twitter:description" content="[^"]*"/,
          `<meta name="twitter:description" content="${meta.desc}"`,
        );

        // Replace noscript content
        html = html.replace(
          /<noscript>[\s\S]*?<\/noscript>/,
          `<noscript><div style="max-width:800px;margin:40px auto;padding:0 24px;font-family:serif;color:#2b2318">${meta.noscript}</div></noscript>`,
        );

        const dir = resolve(distDir, route);
        mkdirSync(dir, { recursive: true });
        writeFileSync(resolve(dir, "index.html"), html);
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
  if (id.includes("/node_modules/antd/")) {
    return "vendor-antd";
  }
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
        globPatterns: ["**/*.{js,css,html,ico,png,svg,webp}"],
        globIgnores: ["**/landscape-bg.png"],
        navigateFallbackDenylist: [/^\/api\//],
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
