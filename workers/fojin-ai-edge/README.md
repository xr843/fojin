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
| `/` | **302 → `https://fojin.app/agents`** — the agent portal's short address |
| everything else | **301 → `https://fojin.app<path><query>`** |

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
