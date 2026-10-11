/**
 * Build-time crawler shells, one per (route × UI language).
 *
 * `seoPages()` in vite.config.ts stamps each entry of `shellPlan()` into
 * `dist/<outFile>`; frontend/nginx.conf picks the file by `?lang=` (a `map` on
 * `$arg_lang` → `index{.zh-Hant|.en}.html`). Every variant declares its own
 * `<html lang>`, self-referencing canonical and — for indexable routes — the
 * four hreflang alternates, using the same URL rule as the runtime <Helmet>
 * (./langUrl.ts) and the backend (app/services/seo_lang.py).
 * See docs/superpowers/specs/2026-10-11-i18n-seo-design.md.
 *
 * Kept as pure functions over plain data so the copy and the stamping are
 * unit-testable without running a build.
 */
import * as OpenCC from "opencc-js";
import collectionsEn from "../content/collectionLocales/en.json";
import collectionsZhHant from "../content/collectionLocales/zh-Hant.json";
import collectionsZh from "../content/collectionLocales/zh.json";
import sutrasEn from "../content/sutraLocales/en.json";
import sutrasZhHant from "../content/sutraLocales/zh-Hant.json";
import localeEn from "../../public/locales/en/translation.json";
import localeZhHant from "../../public/locales/zh-Hant/translation.json";
import localeZh from "../../public/locales/zh/translation.json";
import { langUrl, ogLocaleFor, type SeoLang } from "./langUrl";
import { STATIC_SEO_PAGES, type SeoPage } from "./staticPages";

const cnToTw = OpenCC.Converter({ from: "cn", to: "tw" });

export function toTraditional(s: string): string {
  return cnToTw(s);
}

const HTML_LANG: Record<SeoLang, string> = { zh: "zh-Hans", "zh-Hant": "zh-Hant", en: "en" };
const LANGS: SeoLang[] = ["zh", "zh-Hant", "en"];
const SUFFIX: Record<SeoLang, string> = { zh: "", "zh-Hant": ".zh-Hant", en: ".en" };

/** Routes whose shells must not advertise language alternates. */
const NO_HREFLANG = new Set(["search"]);

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeText(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function hreflangTags(path: string): string {
  return [
    `<link rel="alternate" hreflang="zh-Hans" href="${langUrl(path, "zh")}" />`,
    `<link rel="alternate" hreflang="zh-Hant" href="${langUrl(path, "zh-Hant")}" />`,
    `<link rel="alternate" hreflang="en" href="${langUrl(path, "en")}" />`,
    `<link rel="alternate" hreflang="x-default" href="${langUrl(path, "zh")}" />`,
  ].join("\n    ");
}

export interface ShellOptions {
  lang: SeoLang;
  /** URL path the shell is served at, e.g. "/chat" or "/". */
  path: string;
  meta: SeoPage;
  hreflang: boolean;
}

/** Replace a tag's attribute value; the replacement is a function so `$` in copy is never a backreference. */
function sub(html: string, re: RegExp, replacement: string): string {
  return html.replace(re, () => replacement);
}

export function localizeShell(template: string, { lang, path, meta, hreflang }: ShellOptions): string {
  const url = langUrl(path, lang);
  const title = escapeText(meta.title);
  const titleAttr = escapeAttr(meta.title);
  const desc = escapeAttr(meta.desc);
  let html = template;
  html = sub(html, /<html lang="[^"]*"/, `<html lang="${HTML_LANG[lang]}"`);
  html = sub(html, /<title>[^<]*<\/title>/, `<title>${title}</title>`);
  html = sub(html, /<meta name="description" content="[^"]*"/, `<meta name="description" content="${desc}"`);
  html = sub(html, /<link rel="canonical" href="[^"]*"/, `<link rel="canonical" href="${url}"`);
  html = sub(html, /<meta property="og:url" content="[^"]*"/, `<meta property="og:url" content="${url}"`);
  html = sub(html, /<meta property="og:title" content="[^"]*"/, `<meta property="og:title" content="${titleAttr}"`);
  html = sub(html, /<meta property="og:description" content="[^"]*"/, `<meta property="og:description" content="${desc}"`);
  html = sub(html, /<meta property="og:locale" content="[^"]*"/, `<meta property="og:locale" content="${ogLocaleFor(lang)}"`);
  html = sub(html, /<meta name="twitter:title" content="[^"]*"/, `<meta name="twitter:title" content="${titleAttr}"`);
  html = sub(html, /<meta name="twitter:description" content="[^"]*"/, `<meta name="twitter:description" content="${desc}"`);
  html = sub(html, /"inLanguage": "[^"]*"/, `"inLanguage": "${HTML_LANG[lang]}"`);
  html = sub(html, /<meta property="og:image:alt" content="[^"]*"/, `<meta property="og:image:alt" content="${titleAttr}"`);
  // zh / zh-Hant keep the template's bilingual site name as-is.
  if (lang === "en") html = sub(html, /<meta property="og:site_name" content="[^"]*"/, '<meta property="og:site_name" content="FoJin"');
  html = sub(
    html,
    /<noscript>[\s\S]*?<\/noscript>/,
    `<noscript><div style="max-width:800px;margin:40px auto;padding:0 24px;font-family:serif;color:#2b2318">${meta.noscript}</div></noscript>`,
  );
  if (hreflang) {
    html = sub(html, /<\/head>/, `  ${hreflangTags(path)}\n  </head>`);
  }
  return html;
}

export interface ShellEntry extends ShellOptions {
  /** Output path relative to dist/, e.g. "chat/index.en.html". */
  outFile: string;
}

type Locale = Record<string, unknown>;
const LOCALES: Record<SeoLang, Locale> = {
  zh: localeZh as Locale,
  "zh-Hant": localeZhHant as Locale,
  en: localeEn as Locale,
};

function localeString(lang: SeoLang, key: string): string {
  const value = LOCALES[lang][key];
  if (typeof value !== "string") throw new Error(`missing locale key ${lang}:${key}`);
  return value;
}

/** Copy for the home page. zh comes from index.html itself (the template). */
function homeMeta(lang: SeoLang, zh: SeoPage): SeoPage {
  if (lang === "zh") return zh;
  if (lang === "zh-Hant") {
    return { title: localeString("zh-Hant", "app.title"), desc: toTraditional(zh.desc), noscript: toTraditional(zh.noscript) };
  }
  return {
    title: localeString("en", "app.title"),
    desc:
      "Ask the Buddhist canon and get answers you can check: every citation names the sutra and fascicle and opens the original text. Chinese, Pali and Tibetan parallels side by side, with public Buddhist texts and dictionaries from around the world. Free.",
    noscript:
      "<h1>FoJin — Ask the Buddhist canon, check every citation</h1><p>XiaoJin answers from the original texts. Every citation names the sutra and fascicle and opens the source, so you can verify it yourself.</p><ul><li>AI Q&amp;A grounded in the canon</li><li>Chinese, Pali, Sanskrit and Tibetan parallels side by side</li><li>Buddhist dictionaries and public digital collections in one place</li></ul>",
  };
}

function templateMeta(template: string): SeoPage {
  const title = /<title>([^<]*)<\/title>/.exec(template)?.[1] ?? "";
  const desc = /<meta name="description" content="([^"]*)"/.exec(template)?.[1] ?? "";
  const noscript = /<noscript>\s*<div[^>]*>([\s\S]*?)<\/div>\s*<\/noscript>/.exec(template)?.[1] ?? "";
  return { title, desc, noscript };
}

interface SutraLocale {
  title: string;
  metaTitle: string;
  metaDescription: string;
}

function sutraMeta(lang: SeoLang, slug: string, zh: SeoPage): SeoPage {
  if (lang === "zh") return zh;
  const table = (lang === "en" ? sutrasEn : sutrasZhHant) as Record<string, SutraLocale>;
  const s = table[slug];
  if (!s) throw new Error(`sutraLocales/${lang} has no ${slug}`);
  return { title: s.metaTitle, desc: s.metaDescription, noscript: `<h1>${escapeText(s.title)}</h1><p>${escapeText(s.metaDescription)}</p>` };
}

interface CollectionLocale {
  id: string;
  name: string;
  description: string;
  mainTexts?: Array<{ title: string }>;
}

const COLLECTIONS: Record<SeoLang, CollectionLocale[]> = {
  zh: (collectionsZh as { collections: CollectionLocale[] }).collections,
  "zh-Hant": (collectionsZhHant as { collections: CollectionLocale[] }).collections,
  en: (collectionsEn as { collections: CollectionLocale[] }).collections,
};

function collectionMeta(lang: SeoLang, c: CollectionLocale): SeoPage {
  const title = localeString(lang, "collections.detail_page_title").replace("{{name}}", c.name);
  const texts = (c.mainTexts ?? []).map((t) => `<li>${escapeText(t.title)}</li>`).join("");
  return {
    title,
    desc: c.description,
    noscript: `<h1>${escapeText(c.name)}</h1><p>${escapeText(c.description)}</p>${texts ? `<ul>${texts}</ul>` : ""}`,
  };
}

function staticMeta(lang: SeoLang, route: string): SeoPage {
  const page = STATIC_SEO_PAGES[route];
  const zh: SeoPage = { title: page.title, desc: page.desc, noscript: page.noscript };
  if (lang === "zh") return zh;
  if (lang === "zh-Hant") {
    return { title: toTraditional(zh.title), desc: toTraditional(zh.desc), noscript: toTraditional(zh.noscript) };
  }
  if (!page.en) throw new Error(`staticPages.json: ${route} has no en copy`);
  return page.en;
}

/**
 * Every shell the build writes. The template `index.html` itself is not in the
 * plan: it stays the zh SPA fallback exactly as Vite emitted it.
 */
export function shellPlan(template?: string): ShellEntry[] {
  const zhHome = templateMeta(template ?? "");
  const out: ShellEntry[] = [];
  for (const lang of LANGS) {
    const sfx = SUFFIX[lang];
    const home = homeMeta(lang, zhHome);
    // Home page: served by `location = /`, carries hreflang.
    out.push({ outFile: `_home/index${sfx}.html`, lang, path: "/", meta: home, hreflang: true });
    // Generic SPA fallback for every route without its own shell: language only.
    if (lang !== "zh") out.push({ outFile: `index${sfx}.html`, lang, path: "/", meta: home, hreflang: false });

    for (const route of Object.keys(STATIC_SEO_PAGES)) {
      const meta = route.startsWith("sutras/")
        ? sutraMeta(lang, route.slice("sutras/".length), staticMeta("zh", route))
        : staticMeta(lang, route);
      out.push({ outFile: `${route}/index${sfx}.html`, lang, path: `/${route}`, meta, hreflang: !NO_HREFLANG.has(route) });
    }
    for (const c of COLLECTIONS[lang]) {
      out.push({
        outFile: `collections/${c.id}/index${sfx}.html`,
        lang,
        path: `/collections/${c.id}`,
        meta: collectionMeta(lang, c),
        hreflang: true,
      });
    }
  }
  return out;
}
