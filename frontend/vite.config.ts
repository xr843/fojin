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
        '<h1>佛津 — 典籍搜索</h1><p>跨 503 个数据源检索佛教古籍，支持按经名、编号、译者查询。</p><a href="/">返回首页</a>',
    },
    sources: {
      title: "数据源导航 | 佛津 FoJin",
      desc: "聚合全球 503 个佛教数字资源，覆盖图书馆、大学、研究机构、数字项目等。",
      noscript:
        '<h1>佛津 — 数据源导航</h1><p>聚合 CBETA、BDRC、SAT、SuttaCentral 等全球 503 个佛教数字资源。</p><a href="/">返回首页</a>',
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
    topics: {
      title: "经典专题 — 佛津 FoJin",
      desc: "按主题浏览佛教经典：般若系、净土五经、法华系、禅宗典籍、律藏、阿含经、唯识经论、华严系。",
      noscript:
        '<h1>佛津 — 经典专题</h1><p>按主题浏览佛教经典，帮助您找到入门路径。</p><a href="/">返回首页</a>',
    },
    dictionary: {
      title: "佛学辞典 — 佛津 FoJin",
      desc: "38 部权威佛学辞典，712,000+ 词条，覆盖中梵巴藏英五语。在线查询佛光大辞典、丁福保佛学大辞典、Digital Pali Dictionary 等权威辞典。",
      noscript:
        '<h1>佛津 — 佛学辞典</h1><p>聚合 38 部权威佛学辞典，超过 712,000 条词条，覆盖中文、梵文、巴利文、藏文、英文五种语言。</p><h2>收录辞典</h2><ul><li>佛光大辞典</li><li>丁福保佛学大辞典</li><li>Digital Pali Dictionary (DPD)</li><li>Sanskrit Heritage Dictionary</li><li>Monier-Williams Sanskrit-English Dictionary</li><li>Buddhist Hybrid Sanskrit Dictionary</li><li>翻译名义集</li><li>一切经音义</li></ul><a href="/">返回首页</a>',
    },
    // Sutra landing pages
    "sutras/heart-sutra": {
      title: "心经全文 — 般若波罗蜜多心经原文在线阅读 | 佛津 FoJin",
      desc: "心经全文在线阅读。《般若波罗蜜多心经》为唐玄奘译，全经仅260字，是般若经典的精髓总结，阐明五蕴皆空的核心义理。",
      noscript: '<h1>心经全文 — 般若波罗蜜多心经</h1><p>唐玄奘译，全经仅260字，般若经典精髓。</p><a href="/">返回首页</a>',
    },
    "sutras/diamond-sutra": {
      title: "金刚经全文 — 金刚般若波罗蜜经原文在线阅读 | 佛津 FoJin",
      desc: "金刚经全文在线阅读。《金刚般若波罗蜜经》为姚秦鸠摩罗什译，阐述「应无所住而生其心」的般若空慧。",
      noscript: '<h1>金刚经全文 — 金刚般若波罗蜜经</h1><p>姚秦鸠摩罗什译，般若空慧经典。</p><a href="/">返回首页</a>',
    },
    "sutras/lotus-sutra": {
      title: "法华经全文 — 妙法莲华经原文在线阅读 | 佛津 FoJin",
      desc: "法华经全文在线阅读。《妙法莲华经》七卷二十八品，姚秦鸠摩罗什译，宣说一佛乘思想，天台宗根本经典。",
      noscript: '<h1>法华经全文 — 妙法莲华经</h1><p>姚秦鸠摩罗什译，天台宗根本经典。</p><a href="/">返回首页</a>',
    },
    "sutras/avatamsaka-sutra": {
      title: "华严经全文 — 大方广佛华严经原文在线阅读 | 佛津 FoJin",
      desc: "华严经全文在线阅读。《大方广佛华严经》六十卷，东晋佛驮跋陀罗译，华严宗根本经典。",
      noscript: '<h1>华严经全文 — 大方广佛华严经</h1><p>东晋佛驮跋陀罗译，华严宗根本经典。</p><a href="/">返回首页</a>',
    },
    "sutras/shurangama-sutra": {
      title: "楞严经全文 — 首楞严经原文在线阅读 | 佛津 FoJin",
      desc: "楞严经全文在线阅读。《首楞严经》十卷，唐般剌蜜帝译，详述二十五圆通法门与五十阴魔境界。",
      noscript: '<h1>楞严经全文 — 首楞严经</h1><p>唐般剌蜜帝译，禅宗与密宗重要经典。</p><a href="/">返回首页</a>',
    },
    "sutras/amitabha-sutra": {
      title: "阿弥陀经全文 — 佛说阿弥陀经原文在线阅读 | 佛津 FoJin",
      desc: "阿弥陀经全文在线阅读。《佛说阿弥陀经》姚秦鸠摩罗什译，净土宗根本经典，阐明持名念佛往生净土法门。",
      noscript: '<h1>阿弥陀经全文 — 佛说阿弥陀经</h1><p>姚秦鸠摩罗什译，净土宗根本经典。</p><a href="/">返回首页</a>',
    },
    "sutras/ksitigarbha-sutra": {
      title: "地藏经全文 — 地藏菩萨本愿经原文在线阅读 | 佛津 FoJin",
      desc: "地藏经全文在线阅读。《地藏菩萨本愿经》唐实叉难陀译，记述地藏菩萨大愿与度生功德。",
      noscript: '<h1>地藏经全文 — 地藏菩萨本愿经</h1><p>唐实叉难陀译，佛门孝经。</p><a href="/">返回首页</a>',
    },
    "sutras/medicine-buddha-sutra": {
      title: "药师经全文 — 药师琉璃光如来本愿功德经在线阅读 | 佛津 FoJin",
      desc: "药师经全文在线阅读。《药师琉璃光如来本愿功德经》唐玄奘译，记述药师佛十二大愿与消灾延寿法门。",
      noscript: '<h1>药师经全文 — 药师琉璃光如来本愿功德经</h1><p>唐玄奘译，消灾延寿法门。</p><a href="/">返回首页</a>',
    },
    "sutras/platform-sutra": {
      title: "六祖坛经全文 — 法宝坛经原文在线阅读 | 佛津 FoJin",
      desc: "六祖坛经全文在线阅读。《六祖大师法宝坛经》记录禅宗六祖惠能大师开示法语，中国佛教唯一被尊称为「经」的祖师著述。",
      noscript: '<h1>六祖坛经全文 — 法宝坛经</h1><p>禅宗六祖惠能大师开示法语。</p><a href="/">返回首页</a>',
    },
    "sutras/vimalakirti-sutra": {
      title: "维摩诘经全文 — 维摩诘所说经原文在线阅读 | 佛津 FoJin",
      desc: "维摩诘经全文在线阅读。《维摩诘所说经》三卷十四品，姚秦鸠摩罗什译，展现大乘不二法门与在家修行的殊胜。",
      noscript: '<h1>维摩诘经全文 — 维摩诘所说经</h1><p>姚秦鸠摩罗什译，不二法门经典。</p><a href="/">返回首页</a>',
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
        skipWaiting: true,
        clientsClaim: true,
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
