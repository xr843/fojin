// fojin.ai edge worker (deployed as `fojin-ai-sw-killswitch`).
//
// fojin.ai is the app's former domain. This worker has two jobs:
//
//   1. Un-register the legacy service worker that domain left behind in
//      returning visitors' browsers. A stale SW would keep serving the old
//      app from its own cache and never see the redirect below, so /sw.js
//      and /registerSW.js answer with scripts whose only purpose is to drop
//      every cache, unregister themselves, and navigate the client onward.
//      Browsers re-fetch a registered SW script at least every 24h, which is
//      what makes this eventually reach everyone. Do not remove.
//
//   2. Serve fojin.ai's own site: the 引文溯源 page at / ("does this passage
//      come from the canon?", proxied from fojin.app/trace.html), the
//      Master-skill catalogue at /masters (forwarded from the Master-skill
//      repo's Pages site), the agent portal at /developers (proxied from
//      fojin.app/agents.html), and send every other path to fojin.app,
//      path-preserving.
//
// The worker predates this directory: it was created and routed by hand in
// the Cloudflare dashboard, and the source lived nowhere. This file is that
// source, recovered from the deployed script so the next change is a diff
// rather than an archaeology exercise. See README.md for how to deploy.

const KILL_SW = `// fojin.ai kill-switch service worker
self.addEventListener('install', (event) => {
  self.skipWaiting();
});
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (e) {}
    try {
      await self.registration.unregister();
    } catch (e) {}
    const clients = await self.clients.matchAll({ type: 'window' });
    for (const client of clients) {
      const target = client.url.replace(/^https?:\\/\\/(www\\.)?fojin\\.ai/, 'https://fojin.app');
      try { client.navigate(target); } catch (e) {}
    }
  })());
});
// Never intercept — always hit network (which will redirect to fojin.app)
self.addEventListener('fetch', () => {});
`;

const KILL_REGISTER_SW = `// fojin.ai kill-switch registerSW
(async () => {
  if ('serviceWorker' in navigator) {
    try {
      const regs = await navigator.serviceWorker.getRegistrations();
      for (const r of regs) { try { await r.unregister(); } catch (e) {} }
    } catch (e) {}
    try {
      await navigator.serviceWorker.register('/sw.js', { scope: '/' });
    } catch (e) {}
  }
  if (typeof caches !== 'undefined') {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (e) {}
  }
  const here = location.href;
  const target = here.replace(/^https?:\\/\\/(www\\.)?fojin\\.ai/, 'https://fojin.app');
  if (target !== here) {
    location.replace(target);
  }
})();
`;

const JS_HEADERS = {
  "content-type": "application/javascript; charset=utf-8",
  "cache-control": "no-store, no-cache, must-revalidate",
  "service-worker-allowed": "/",
};

// The Master-skill catalogue (fojin.ai/masters) is built and published by the
// Master-skill repository (site/, Cloudflare Pages project `master-skill`),
// where it is that site's "/". This worker forwards only these paths to it; every other
// path keeps the behaviour below, so old fojin.ai deep links still 301.
// /_site/ is a deliberately unusual prefix: the old PWA used /assets/, and
// those URLs must keep redirecting rather than 404 on the new site.
const SITE_ORIGIN = "https://master-skill.pages.dev";
// robots.txt / sitemap.xml are fojin.ai's own (written by the Master-skill
// build) — without them crawlers were sent to fojin.app's.
// Keyed by the fojin.ai path; the value is the path on the Pages site.
const SITE_PATHS = new Map([
  ["/masters", "/"],
  ["/robots.txt", "/robots.txt"],
  ["/sitemap.xml", "/sitemap.xml"],
]);
const SITE_PREFIX = "/_site/";

// Security headers for pages this worker serves itself. Mirrors the fojin.app
// policy: no inline script, analytics only from analytics.fojin.app.
const SITE_CSP = [
  "default-src 'self'",
  "script-src 'self' https://analytics.fojin.app",
  // fojin.app: the 引文溯源 page calls /api/verify/trace there directly, so the
  // rate limit counts each visitor's own IP (via this Worker it saw the
  // Worker's egress address for everyone). Possible since the host nginx stopped
  // doubling the CORS header (deploy/host-nginx/README.md, conflict 2).
  "connect-src 'self' https://fojin.app https://analytics.fojin.app",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
].join("; ");

// Paths proxied from fojin.app as-is. /developers is the agent portal
// (fojin.app/agents.html — MCP endpoint, API, CLI); the others are same-origin
// assets that page and the home page load. They must be proxied, not
// redirected: the CSP is `'self'`, and a redirect would take the script and
// the title font off-origin, where the CSP blocks them.
// Add a path here if agents.html starts loading another root-relative asset.
const PORTAL_PROXY = new Map([
  // The home page: 引文溯源 (frontend/public/trace.html + trace.js).
  ["/", "/trace.html"],
  ["/index.html", "/trace.html"],
  ["/trace.js", "/trace.js"],
  // The file, not /agents: fojin.app/agents 301s to fojin.ai/developers, so
  // fetching it would bounce straight back here.
  ["/developers", "/agents.html"],
  ["/theme-init.js", "/theme-init.js"],
  ["/favicon.svg", "/favicon.svg"],
  ["/fonts/MaShanZheng-title-v2.woff2", "/fonts/MaShanZheng-title-v2.woff2"],
]);

async function proxyFromApp(path, request) {
  try {
    const upstream = await fetch("https://fojin.app" + path, {
      method: request.method,
      headers: { accept: request.headers.get("accept") || "*/*" },
      redirect: "manual",
    });
    if (upstream.status !== 200) return null;
    return new Response(upstream.body, upstream);
  } catch (e) {
    return null;
  }
}

async function serveSite(request) {
  const url = new URL(request.url);
  const path = SITE_PATHS.get(url.pathname) || url.pathname;
  let res;
  try {
    res = await fetch(SITE_ORIGIN + path, {
      method: request.method,
      headers: { accept: request.headers.get("accept") || "*/*" },
      redirect: "manual",
    });
  } catch (e) {
    return null;
  }
  if (res.status !== 200) return null;
  // Pages answers an unknown path with the home page (SPA fallback). Only "/"
  // is meant to be HTML; any other path that comes back as HTML does not exist
  // on the site (a missing /_site/ asset, or robots.txt before it is built).
  if (path !== "/" && (res.headers.get("content-type") || "").startsWith("text/html")) {
    return null;
  }
  const out = new Response(res.body, res);
  out.headers.set("content-security-policy", SITE_CSP);
  out.headers.set("x-content-type-options", "nosniff");
  out.headers.set("referrer-policy", "strict-origin-when-cross-origin");
  if ((out.headers.get("content-type") || "").startsWith("text/html")) {
    // HTML revalidates every visit so a new Master-skill deploy shows at once.
    out.headers.set("cache-control", "public, max-age=0, must-revalidate");
  }
  return out;
}

// Fallback only: the 引文溯源 page now calls fojin.app directly (per-visitor
// rate limit). This same-origin pass-through stays for pages still cached with
// the old script; it can go once that cache has turned over.
// The 引文溯源 page used to post to /api/verify/trace on its own origin; this worker
// passes it to fojin.app. Calling fojin.app cross-origin does not work: the
// host nginx adds `Access-Control-Allow-Origin: *` to every /api/ response on
// top of FastAPI's own `https://fojin.ai`, and browsers reject the doubled
// header (deploy/host-nginx/README.md, known conflict 2). Cost: rate limiting
// sees this worker's address, so fojin.ai visitors share one per-minute window
// (6 calls) — fine at today's traffic; the page waits out a 429 and resumes.
const API_PASSTHROUGH = new Set(["/api/verify/trace"]);

async function passApi(request, url) {
  try {
    const upstream = await fetch("https://fojin.app" + url.pathname + url.search, {
      method: request.method,
      headers: {
        "content-type": request.headers.get("content-type") || "application/json",
        accept: "application/json",
      },
      body: request.method === "POST" ? await request.text() : undefined,
      redirect: "manual",
    });
    const out = new Response(upstream.body, upstream);
    // Same-origin now: drop the doubled CORS headers fojin.app sends.
    for (const h of [...out.headers.keys()]) {
      if (h.startsWith("access-control-")) out.headers.delete(h);
    }
    out.headers.set("cache-control", "no-store");
    return out;
  } catch (e) {
    return new Response(JSON.stringify({ detail: "upstream unavailable" }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }
}

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (API_PASSTHROUGH.has(url.pathname) && request.method === "POST") {
      return passApi(request, url);
    }

    if (url.pathname === "/sw.js") {
      return new Response(KILL_SW, { headers: JS_HEADERS });
    }
    if (url.pathname === "/registerSW.js") {
      return new Response(KILL_REGISTER_SW, { headers: JS_HEADERS });
    }

    const readOnly = request.method === "GET" || request.method === "HEAD";

    if (readOnly && (SITE_PATHS.has(url.pathname) || url.pathname.startsWith(SITE_PREFIX))) {
      const served = await serveSite(request);
      if (served) return served;
      if (url.pathname === "/masters") {
        // Master-skill site unreachable: the catalogue's install docs on GitHub.
        return Response.redirect("https://github.com/xr843/Master-skill#readme", 302);
      }
      if (url.pathname.startsWith(SITE_PREFIX)) {
        return new Response("Not found", { status: 404 });
      }
      // robots.txt / sitemap.xml not on the site yet: fall through to the
      // reader's copy (the 301 below), as before.
    }

    const upstreamPath = PORTAL_PROXY.get(url.pathname);
    if (upstreamPath && readOnly) {
      // /trace.js?v=N: the query is the cache-buster for Cloudflare's 4-hour
      // .js cache at fojin.app, so it must reach fojin.app.
      const upstream = url.pathname === "/trace.js" ? upstreamPath + url.search : upstreamPath;
      const served = await proxyFromApp(upstream, request);
      const isPage = url.pathname === "/developers" || url.pathname === "/" || url.pathname === "/index.html";
      if (served && isPage) {
        // A fojin.ai page now (same header, same /_site/ scripts as the home
        // page), so it gets the home page's headers, not fojin.app's.
        served.headers.set("content-security-policy", SITE_CSP);
        served.headers.set("cache-control", "public, max-age=0, must-revalidate");
        return served;
      }
      if (served) return served;
      // fojin.app unreachable or not 200: 302 rather than 301 — a permanent
      // redirect cached in clients cannot be taken back.
      if (url.pathname === "/developers") {
        // Not fojin.app/agents — that now redirects back to this page.
        return Response.redirect("https://fojin.app/docs", 302);
      }
      if (url.pathname === "/" || url.pathname === "/index.html") {
        // fojin.app unreachable: the same check, one sentence at a time.
        return Response.redirect("https://fojin.app/verify", 302);
      }
    }

    // Every other path keeps its permanent, path-preserving redirect to the
    // reader, so old fojin.ai deep links still land where they used to.
    const target = new URL(url.pathname + url.search, "https://fojin.app");
    return Response.redirect(target.toString(), 301);
  },
};
