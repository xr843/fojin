export interface TextData {
  id: number;
  title_zh?: string | null;
  title_sa?: string | null;
  translator?: string | null;
  dynasty?: string | null;
  category?: string | null;
  cbeta_id?: string | null;
  lang?: string | null;
}

const SITE = "https://fojin.app";
const SITE_NAME = "佛津 FoJin";

/** Escape HTML special characters to prevent XSS in rendered output. */
function esc(text: string | null | undefined): string {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Escape a value for embedding inside a JSON string that lives in a <script> tag. */
function jsonEsc(text: string | null | undefined): string {
  if (!text) return "";
  return text
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e");
}

function buildDescription(d: TextData): string {
  const parts: string[] = [];
  if (d.title_zh) parts.push(d.title_zh);
  if (d.translator) parts.push(`${d.translator}译`);
  if (d.dynasty) parts.push(d.dynasty);
  if (d.category) parts.push(d.category);
  parts.push("佛津佛教古籍数字资源平台");
  return parts.join(" · ");
}

function buildJsonLd(textId: string, d: TextData): string {
  const obj: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Book",
    name: d.title_zh || `Text ${textId}`,
    url: `${SITE}/texts/${textId}`,
    isPartOf: {
      "@type": "Collection",
      name: "佛津 FoJin 佛教古籍数字资源",
      url: `${SITE}/`,
    },
    provider: {
      "@type": "WebSite",
      name: SITE_NAME,
      url: `${SITE}/`,
    },
  };

  if (d.title_sa) obj.alternateName = d.title_sa;
  if (d.lang) obj.inLanguage = d.lang;
  if (d.translator) {
    obj.translator = { "@type": "Person", name: d.translator };
  }
  if (d.dynasty) obj.temporalCoverage = d.dynasty;
  if (d.category) obj.genre = d.category;

  // Escape </ sequences so the JSON-LD block doesn't break the HTML parser
  return JSON.stringify(obj, null, 2).replace(/<\//g, "<\\/");
}

function dl(label: string, value: string | null | undefined): string {
  if (!value) return "";
  return `        <dt>${esc(label)}</dt><dd>${esc(value)}</dd>\n`;
}

export function renderTextPage(textId: string, data: TextData): string {
  const title = data.title_zh || `Text ${textId}`;
  const description = buildDescription(data);
  const canonical = `${SITE}/texts/${textId}`;
  const escapedTitle = esc(title);
  const escapedDesc = esc(description);

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapedTitle} — 佛津</title>
  <meta name="description" content="${escapedDesc}">
  <link rel="canonical" href="${canonical}">

  <!-- Open Graph -->
  <meta property="og:type" content="book">
  <meta property="og:title" content="${escapedTitle} — 佛津">
  <meta property="og:description" content="${escapedDesc}">
  <meta property="og:url" content="${canonical}">
  <meta property="og:site_name" content="${esc(SITE_NAME)}">
  <meta property="og:locale" content="zh_CN">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="${escapedTitle} — 佛津">
  <meta name="twitter:description" content="${escapedDesc}">

  <!-- JSON-LD Structured Data -->
  <script type="application/ld+json">
${buildJsonLd(textId, data)}
  </script>
</head>
<body>
  <div style="max-width:800px;margin:40px auto;padding:0 24px;font-family:serif;color:#2b2318">
    <header>
      <h1>${escapedTitle}</h1>
      <nav><a href="/">首页</a> &gt; <a href="/search">搜索</a> &gt; 经典详情</nav>
    </header>
    <main>
      <dl>
${dl("CBETA 编号", data.cbeta_id)}${dl("译者", data.translator)}${dl("朝代", data.dynasty)}${dl("分类", data.category)}${dl("梵文题名", data.title_sa)}      </dl>
      <p><a href="/texts/${esc(textId)}/read">阅读全文</a></p>
    </main>
    <footer>
      <p><a href="/">佛津 FoJin</a> — 全球佛教古籍数字资源聚合平台</p>
    </footer>
  </div>
</body>
</html>`;
}
