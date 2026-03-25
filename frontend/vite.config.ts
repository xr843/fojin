/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { resolve } from "path";
import { mkdirSync, writeFileSync, readFileSync } from "fs";

/**
 * 为关键路由生成独立 HTML 文件，让搜索引擎无需 JS 即可获取正确的
 * title / description / noscript 内容。Nginx/CDN 对 /sources 返回
 * dist/sources/index.html，爬虫直接拿到正确 meta。
 */
function seoPages(): Plugin {
  const pages: Record<string, { title: string; desc: string; noscript: string }> = {
    search: {
      title: "搜索 | 佛津 FoJin",
      desc: "搜索全球佛教古籍数字资源 — 支持按经名、编号、译者检索",
      noscript:
        '<h1>佛津 — 典籍搜索</h1><p>跨 40+ 数据源检索佛教古籍，支持按经名、编号、译者查询。</p><a href="/">返回首页</a>',
    },
    sources: {
      title: "数据源导航 | 佛津 FoJin",
      desc: "聚合全球 40+ 佛教数字资源，覆盖图书馆、大学、研究机构、数字项目等。",
      noscript:
        '<h1>佛津 — 数据源导航</h1><p>聚合 CBETA、BDRC、SAT、SuttaCentral 等全球 40 余个佛教数字资源。</p><a href="/">返回首页</a>',
    },
    kg: {
      title: "知识图谱 | 佛津 FoJin",
      desc: "佛教知识图谱 — 人物、寺院、宗派关系可视化",
      noscript:
        '<h1>佛津 — 知识图谱</h1><p>可视化展示佛教人物、寺院、宗派之间的关系网络。</p><a href="/">返回首页</a>',
    },
    collections: {
      title: "藏经收藏 | 佛津 FoJin",
      desc: "浏览和管理您的佛教古籍收藏集合",
      noscript:
        '<h1>佛津 — 藏经收藏</h1><p>浏览和管理您的佛教古籍收藏集合。</p><a href="/">返回首页</a>',
    },
  };

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

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: false, // We provide our own manifest.json in public/
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg}"],
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
    seoPages(),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-antd": ["antd"],
          "vendor-query": ["@tanstack/react-query"],
          "vendor-d3": ["d3"],
          "source-urls": ["./src/utils/sourceUrls"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
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
