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
//   2. Send the domain's traffic to fojin.app, path-preserving — except the
//      bare root, which is the short address of the agent portal.
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

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === "/sw.js") {
      return new Response(KILL_SW, { headers: JS_HEADERS });
    }
    if (url.pathname === "/registerSW.js") {
      return new Response(KILL_REGISTER_SW, { headers: JS_HEADERS });
    }

    // The bare domain is the agent portal's short address: fojin.ai is the
    // AI-facing name, and /agents is that front door. 302 rather than 301 —
    // the previous permanent redirect to fojin.app/ is already cached in some
    // clients, so a permanent one here would be just as hard to take back.
    if (url.pathname === "/") {
      return Response.redirect("https://fojin.app/agents", 302);
    }

    // Every other path keeps its permanent, path-preserving redirect to the
    // reader, so old fojin.ai deep links still land where they used to.
    const target = new URL(url.pathname + url.search, "https://fojin.app");
    return Response.redirect(target.toString(), 301);
  },
};
