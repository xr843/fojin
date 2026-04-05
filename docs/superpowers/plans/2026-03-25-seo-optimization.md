# SEO Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FoJin's 9200+ Buddhist text pages discoverable by search engines through dynamic sitemap, structured data, and enhanced meta tags.

**Architecture:** Add a backend `/api/sitemap.xml` endpoint that generates a sitemap index + per-batch sitemaps covering all texts. Enhance the frontend `TextDetailPage` with JSON-LD structured data and full OG/Twitter meta tags via react-helmet-async. Update nginx to properly route pre-built SEO pages and proxy the dynamic sitemap. Update robots.txt to point to the dynamic sitemap.

**Tech Stack:** FastAPI (sitemap endpoint) | React + react-helmet-async (structured data & meta) | nginx (routing) | SQLAlchemy async (text queries)

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/app/api/sitemap.py` | Dynamic sitemap XML generation endpoint |
| Modify | `backend/app/main.py:178-221` | Register sitemap router (no `/api` prefix) |
| Modify | `backend/app/services/text.py` | Add `get_all_text_ids_updated()` for sitemap |
| Modify | `frontend/src/pages/TextDetailPage.tsx:97-101` | Enhanced Helmet with OG, Twitter, JSON-LD |
| Modify | `frontend/public/robots.txt` | Point to dynamic sitemap, add crawl-delay |
| Remove | `frontend/public/sitemap.xml` | Replaced by dynamic backend endpoint |
| Modify | `frontend/nginx.conf:69-75` | Add sitemap proxy + SEO page routing |
| Modify | `frontend/vite.config.ts:13-97` | Add collections route to seoPages |

---

### Task 1: Dynamic Sitemap Backend Endpoint

**Files:**
- Create: `backend/app/api/sitemap.py`
- Modify: `backend/app/services/text.py`
- Modify: `backend/app/main.py`

Sitemap spec: max 50,000 URLs per sitemap file. With 9200+ texts we need a sitemap index that references sub-sitemaps. Each text has a detail page (`/texts/{id}`) and optionally a read page (`/texts/{id}/read`). Static pages (/, /search, /sources, /kg, /collections, /chat) go in the first sitemap.

- [ ] **Step 1: Add `get_all_text_ids_updated` to text service**

In `backend/app/services/text.py`, add:

```python
async def get_all_text_ids_updated(session: AsyncSession) -> list[tuple[int, str]]:
    """Return (id, updated_at_date_str) for all texts, ordered by id."""
    from app.models.text import BuddhistText
    result = await session.execute(
        select(BuddhistText.id, BuddhistText.created_at)
        .order_by(BuddhistText.id)
    )
    return [(row[0], row[1].strftime("%Y-%m-%d")) for row in result.all()]
```

- [ ] **Step 2: Create `backend/app/api/sitemap.py`**

```python
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.text import get_all_text_ids_updated

router = APIRouter(tags=["seo"])

SITE = "https://fojin.app"
BATCH_SIZE = 40000  # URLs per sub-sitemap (under 50k limit)

STATIC_PAGES = [
    ("/", "1.0", "weekly"),
    ("/search", "0.9", "daily"),
    ("/sources", "0.8", "weekly"),
    ("/collections", "0.7", "weekly"),
    ("/kg", "0.6", "monthly"),
    ("/chat", "0.5", "monthly"),
]


@router.get("/sitemap.xml")
async def sitemap_index(db: AsyncSession = Depends(get_db)):
    """Sitemap index pointing to sub-sitemaps."""
    texts = await get_all_text_ids_updated(db)
    total = len(texts)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f"  <sitemap><loc>{SITE}/sitemap-static.xml</loc></sitemap>",
    ]
    for i in range(num_batches):
        lines.append(f"  <sitemap><loc>{SITE}/sitemap-texts-{i}.xml</loc></sitemap>")
    lines.append("</sitemapindex>")

    return Response(content="\n".join(lines), media_type="application/xml")


@router.get("/sitemap-static.xml")
async def sitemap_static():
    """Static pages sitemap."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, priority, freq in STATIC_PAGES:
        lines.append(f"  <url><loc>{SITE}{path}</loc><priority>{priority}</priority><changefreq>{freq}</changefreq></url>")
    lines.append("</urlset>")
    return Response(content="\n".join(lines), media_type="application/xml")


@router.get("/sitemap-texts-{batch}.xml")
async def sitemap_texts(batch: int, db: AsyncSession = Depends(get_db)):
    """Text pages sitemap, paginated by batch index."""
    texts = await get_all_text_ids_updated(db)
    start = batch * BATCH_SIZE
    end = start + BATCH_SIZE
    page_texts = texts[start:end]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for text_id, updated in page_texts:
        lines.append(
            f"  <url><loc>{SITE}/texts/{text_id}</loc>"
            f"<lastmod>{updated}</lastmod>"
            f"<priority>0.7</priority><changefreq>monthly</changefreq></url>"
        )
    lines.append("</urlset>")
    return Response(content="\n".join(lines), media_type="application/xml")
```

- [ ] **Step 3: Register sitemap router in main.py (without /api prefix)**

In `backend/app/main.py`, add import and register:

```python
from app.api import sitemap
# ... after all other router registrations:
# SEO: sitemap at root (no /api prefix) so it's served at /sitemap.xml
app.include_router(sitemap.router)
```

- [ ] **Step 4: Test sitemap endpoint locally**

Run: `cd backend && python -c "import app.api.sitemap; print('import ok')"`

Then test with curl:
```bash
curl -s http://localhost:8000/sitemap.xml | head -20
curl -s http://localhost:8000/sitemap-static.xml | head -20
curl -s http://localhost:8000/sitemap-texts-0.xml | head -20
```

Expected: Valid XML responses with correct URLs.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/sitemap.py backend/app/services/text.py backend/app/main.py
git commit -m "feat(seo): add dynamic sitemap.xml with all text pages"
```

---

### Task 2: Update robots.txt & Remove Static Sitemap

**Files:**
- Modify: `frontend/public/robots.txt`
- Remove: `frontend/public/sitemap.xml`

- [ ] **Step 1: Update robots.txt**

Replace `frontend/public/robots.txt` with:

```
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /profile/
Disallow: /login

Sitemap: https://fojin.app/sitemap.xml

# Crawl-delay for polite crawling
Crawl-delay: 1
```

- [ ] **Step 2: Remove static sitemap.xml**

```bash
rm frontend/public/sitemap.xml
```

- [ ] **Step 3: Commit**

```bash
git add frontend/public/robots.txt
git rm frontend/public/sitemap.xml
git commit -m "feat(seo): update robots.txt, remove static sitemap"
```

---

### Task 3: Nginx Routing for Sitemap & SEO Pages

**Files:**
- Modify: `frontend/nginx.conf`

The sitemap requests need to be proxied to the backend. Also, the pre-built SEO pages (search, sources, kg) need explicit nginx routing to serve their own `index.html` files instead of the root `index.html`.

- [ ] **Step 1: Add sitemap proxy and SEO page routing to nginx.conf**

Add before the `/api/` location block:

```nginx
# Dynamic sitemap — proxy to backend
location ~ ^/sitemap.*\.xml$ {
    proxy_pass $upstream_backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cache_valid 200 1h;
}

# Pre-built SEO pages — serve their own index.html with correct meta tags
location = /search {
    try_files /search/index.html /index.html;
}
location = /sources {
    try_files /sources/index.html /index.html;
}
location = /kg {
    try_files /kg/index.html /index.html;
}
location = /collections {
    try_files /collections/index.html /index.html;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/nginx.conf
git commit -m "feat(seo): nginx routing for dynamic sitemap and pre-built SEO pages"
```

---

### Task 4: Enhanced Meta Tags & JSON-LD on TextDetailPage

**Files:**
- Modify: `frontend/src/pages/TextDetailPage.tsx:97-101`

Add full OG tags, Twitter Card tags, canonical URL, and JSON-LD structured data (Book schema) for each text page.

- [ ] **Step 1: Enhance Helmet section in TextDetailPage**

Replace the existing `<Helmet>` block (lines 97-101) with:

```tsx
<Helmet>
  <title>{text.title_zh} — 佛津</title>
  <meta name="description" content={`${text.title_zh}${text.translator ? ` · ${text.translator}译` : ""}${text.dynasty ? ` · ${text.dynasty}` : ""}${text.category ? ` · ${text.category}` : ""} — 佛津佛教古籍数字资源平台`} />
  <link rel="canonical" href={`https://fojin.app/texts/${id}`} />

  {/* Open Graph */}
  <meta property="og:type" content="book" />
  <meta property="og:title" content={`${text.title_zh} — 佛津`} />
  <meta property="og:description" content={`${text.title_zh}${text.translator ? ` · ${text.translator}译` : ""}${text.category ? ` · ${text.category}` : ""}`} />
  <meta property="og:url" content={`https://fojin.app/texts/${id}`} />
  <meta property="og:site_name" content="佛津 FoJin" />
  <meta property="og:locale" content="zh_CN" />

  {/* Twitter Card */}
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content={`${text.title_zh} — 佛津`} />
  <meta name="twitter:description" content={`${text.title_zh}${text.translator ? ` · ${text.translator}译` : ""}${text.category ? ` · ${text.category}` : ""}`} />

  {/* JSON-LD Structured Data */}
  <script type="application/ld+json">
    {JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Book",
      "name": text.title_zh,
      ...(text.title_sa && { "alternateName": text.title_sa }),
      "url": `https://fojin.app/texts/${id}`,
      "inLanguage": text.lang || "lzh",
      ...(text.translator && {
        "translator": { "@type": "Person", "name": text.translator }
      }),
      ...(text.dynasty && {
        "temporalCoverage": text.dynasty
      }),
      ...(text.category && {
        "genre": text.category
      }),
      "isPartOf": {
        "@type": "Collection",
        "name": "佛津 FoJin 佛教古籍数字资源",
        "url": "https://fojin.app/"
      },
      "provider": {
        "@type": "WebSite",
        "name": "佛津 FoJin",
        "url": "https://fojin.app/"
      }
    })}
  </script>
</Helmet>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/TextDetailPage.tsx
git commit -m "feat(seo): add JSON-LD Book schema and full OG/Twitter meta to text pages"
```

---

### Task 5: Add Collections Route to Vite SEO Plugin

**Files:**
- Modify: `frontend/vite.config.ts:13-33`

- [ ] **Step 1: Add collections page to seoPages plugin**

Add to the `pages` object in `seoPages()`:

```typescript
collections: {
  title: "藏经收藏 | 佛津 FoJin",
  desc: "浏览和管理您的佛教古籍收藏集合",
  noscript:
    '<h1>佛津 — 藏经收藏</h1><p>浏览和管理您的佛教古籍收藏集合。</p><a href="/">返回首页</a>',
},
```

- [ ] **Step 2: Commit**

```bash
git add frontend/vite.config.ts
git commit -m "feat(seo): add collections route to Vite SEO pre-render plugin"
```

---

### Task 6: Add Cache Headers for Sitemap Responses

**Files:**
- Modify: `backend/app/api/sitemap.py`

- [ ] **Step 1: Add cache headers to sitemap responses**

Update all three endpoints to include `Cache-Control` header:

```python
return Response(
    content="\n".join(lines),
    media_type="application/xml",
    headers={"Cache-Control": "public, max-age=3600"},  # 1 hour cache
)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/sitemap.py
git commit -m "perf(seo): add 1h cache headers to sitemap responses"
```

---

### Task 7: Verify & Deploy

- [ ] **Step 1: Run backend lint**

```bash
cd backend && ruff check app/api/sitemap.py app/services/text.py app/main.py
```

- [ ] **Step 2: Run frontend lint + type check**

```bash
cd frontend && npx eslint src/pages/TextDetailPage.tsx && npx tsc -b --noEmit
```

- [ ] **Step 3: Test sitemap locally**

```bash
curl -s http://localhost:8000/sitemap.xml
curl -s http://localhost:8000/sitemap-static.xml
curl -s http://localhost:8000/sitemap-texts-0.xml | head -30
```

- [ ] **Step 4: Deploy to production**

Push to master and deploy per CLAUDE.md rules.

- [ ] **Step 5: Verify on production**

```bash
curl -s https://fojin.app/sitemap.xml
curl -s https://fojin.app/robots.txt
```
