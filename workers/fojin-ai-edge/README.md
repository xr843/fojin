# fojin.ai edge worker

Deployed as **`fojin-ai-sw-killswitch`**, routed on `fojin.ai/*` and
`www.fojin.ai/*`. Nothing else runs on that zone — the "fojin.ai 301 to
fojin.app" Redirect Rule in the dashboard is **disabled**, and there are no
Page Rules or Bulk Redirects. If you are trying to work out why fojin.ai
redirects, it is this worker, not a rule.

## What it does

| Path | Response |
| --- | --- |
| `/sw.js` | A service worker whose only job is to drop every cache, unregister itself, and navigate the client to fojin.app |
| `/registerSW.js` | The same clean-up from the page side, for clients that fetch the vite-pwa register shim |
| `/`, `/trace.js` | **fojin.ai's home page** — 引文溯源 (「这段话，出自佛经吗？」): `frontend/public/trace.html` + `trace.js`, fetched from `https://fojin.app`. Falls back to **302 → `https://fojin.app/verify`** |
| `POST /api/verify/trace` | Passed through to `https://fojin.app/api/verify/trace` with fojin.app's CORS headers removed. The page calls its own origin because calling fojin.app cross-origin fails: the host nginx adds `Access-Control-Allow-Origin: *` to every `/api/` response on top of FastAPI's `https://fojin.ai`, and browsers reject the doubled header (`deploy/host-nginx/README.md`, known conflict 2). Cost: rate limiting sees this worker, so fojin.ai visitors share one window |
| `/masters`, `/_site/*`, `/robots.txt`, `/sitemap.xml` | The Master-skill catalogue (its site's `/` served at `/masters`) and fojin.ai's crawler files, forwarded from `https://master-skill.pages.dev` (built from [Master-skill](https://github.com/xr843/Master-skill) `site/`, published on every push to its `main`). Edit the page there, not here. If that site does not answer 200, `/masters` falls back to 302 → the Master-skill README |
| `/developers` | The developer portal (MCP endpoint, API, CLI): `frontend/public/agents.html`, fetched from `https://fojin.app/agents.html` (not `/agents`, which 301s back here). Falls back to 302 → `https://fojin.app/docs` |
| `/theme-init.js`, `/favicon.svg`, `/fonts/MaShanZheng-title-v2.woff2` | Proxied from fojin.app — same-origin assets the pages load; the CSP (`'self'`) would block them if redirected off-origin |
| everything else | **301 → `https://fojin.app<path><query>`** |

## Where to edit fojin.ai

fojin.ai is one site built from two repositories. **This repository (FoJin) is
the default home for fojin.ai changes**; only the master catalogue lives in
Master-skill, because it is generated from that repo's own data (persona
metadata, skill catalogue, install commands — its tests fail when a persona
has no card).

| Change | Edit in | Goes live |
| --- | --- | --- |
| Home page `/` (引文溯源) | here — `frontend/public/trace.html`, `trace.js` (**bump `?v=` in trace.html whenever trace.js changes**: Cloudflare keeps `.js` for 4 hours across deploys) | merge → deploy.sh |
| The check itself (`/api/verify/trace`, `/claim`) | here — `backend/app/api/verification.py`, `services/claim_check.py` | merge → deploy.sh |
| `/developers` | here — `frontend/public/agents.html` | merge → deploy.sh |
| Routing (which path serves what), headers, CSP | here — `workers/fojin-ai-edge/src/index.js` | merge, then **`npx wrangler deploy` by hand** |
| `/masters` (the master catalogue) | [Master-skill](https://github.com/xr843/Master-skill) `site/` | merge → Cloudflare Pages |
| Shared header nav, palette | **all three pages**: `trace.html`, `agents.html`, Master-skill `site/template.html` — they are separate copies today | each repo's own path |

The pages here load `/_site/theme.js` and `/_site/site.js` (light/dark toggle)
from the Master-skill site. Consolidating the shared header, palette and theme
script into this repo is the planned clean-up, due the next time the header
changes.

### Why the kill-switch still matters

fojin.ai is the app's former domain, and the app was a PWA. A visitor who
installed it back then still has a service worker registered on that origin,
and that SW serves the old build from its own cache — it never reaches the
network, so it never sees the redirect. Browsers re-fetch a registered SW
script at least every 24 hours, so answering `/sw.js` with an unregistering
script is what eventually frees those clients. **Do not delete those two
branches**, even though the traffic they serve is invisible in analytics.

## Deploying

The worker predates this directory; it was created in the dashboard and its
source lived nowhere. `src/index.js` was recovered from the deployed script,
so what is here matches what is live.

```bash
cd workers/fojin-ai-edge
npx wrangler deploy          # needs Workers Scripts:Edit on the account
```

If `wrangler` is unavailable, the same upload over the REST API:

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/fojin-ai-sw-killswitch" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -F 'metadata={"main_module":"index.js","compatibility_date":"2026-04-17"};type=application/json' \
  -F 'index.js=@src/index.js;type=application/javascript+module'
```

A script upload does not touch the zone's Worker routes — those are separate
resources — so a bad deploy is recovered by re-uploading, not by re-routing.

## Checking it after a deploy

```bash
curl -sI https://fojin.ai/            | grep -iE '^HTTP|^location'  # 302 → /agents
curl -sI https://fojin.ai/chat        | grep -iE '^HTTP|^location'  # 301 → fojin.app/chat
curl -s  https://fojin.ai/sw.js       | head -3                     # kill-switch SW
curl -sI https://mcp.fojin.ai/healthz | head -1                     # unaffected (own route)
```

Cache-bust with a query string when re-testing: the edge and the browser both
cache these redirects.
