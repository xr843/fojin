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
//   2. Serve fojin.ai's own site: the Master-skill home page at / (forwarded
//      from the Master-skill repo's Pages site), the agent portal at /developers (proxied from
//      fojin.app/agents), and send every other path to fojin.app,
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

// The fojin.ai home page (the Master-skill catalogue) is built and published
// by the Master-skill repository (site/, Cloudflare Pages project
// `master-skill`). This worker forwards only these paths to it; every other
// path keeps the behaviour below, so old fojin.ai deep links still 301.
// /_site/ is a deliberately unusual prefix: the old PWA used /assets/, and
// those URLs must keep redirecting rather than 404 on the new site.
const SITE_ORIGIN = "https://master-skill.pages.dev";
const SITE_PATHS = new Set(["/", "/index.html"]);
const SITE_PREFIX = "/_site/";

// Security headers for pages this worker serves itself. Mirrors the fojin.app
// policy: no inline script, analytics only from analytics.fojin.app.
const SITE_CSP = [
  "default-src 'self'",
  "script-src 'self' https://analytics.fojin.app",
  "connect-src 'self' https://analytics.fojin.app",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
].join("; ");

// Paths proxied from fojin.app as-is. /developers is the agent portal
// (fojin.app/agents — MCP endpoint, API, CLI); the others are same-origin
// assets that page and the home page load. They must be proxied, not
// redirected: the CSP is `'self'`, and a redirect would take the script and
// the title font off-origin, where the CSP blocks them.
// Add a path here if agents.html starts loading another root-relative asset.
const PORTAL_PROXY = new Map([
  ["/developers", "/agents"],
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
  const path = url.pathname === "/index.html" ? "/" : url.pathname;
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
  // Pages answers an unknown path with the home page (SPA fallback). A missing
  // /_site/ asset must be a 404, not a 200 HTML page the browser tries to run.
  if (path.startsWith(SITE_PREFIX) && (res.headers.get("content-type") || "").startsWith("text/html")) {
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

export default {
  async fetch(request) {
    const url = new URL(request.url);

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
      if (url.pathname === "/" || url.pathname === "/index.html") {
        // Master-skill site unreachable: send people to the agent portal
        // rather than the reader, as fojin.ai/ did before it had a site.
        return Response.redirect("https://fojin.app/agents", 302);
      }
      return new Response("Not found", { status: 404 });
    }

    const upstreamPath = PORTAL_PROXY.get(url.pathname);
    if (upstreamPath && readOnly) {
      const served = await proxyFromApp(upstreamPath, request);
      if (served) return served;
      // fojin.app unreachable or not 200: 302 rather than 301 — a permanent
      // redirect cached in clients cannot be taken back.
      if (url.pathname === "/developers") {
        return Response.redirect("https://fojin.app/agents", 302);
      }
    }

    // Every other path keeps its permanent, path-preserving redirect to the
    // reader, so old fojin.ai deep links still land where they used to.
    const target = new URL(url.pathname + url.search, "https://fojin.app");
    return Response.redirect(target.toString(), 301);
  },
};
