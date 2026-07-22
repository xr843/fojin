# Host nginx (the layer above docker-compose)

These files live on the prod VPS at `/etc/nginx/`, **outside** any container.
Until 2026-07-22 they existed only on that machine, which meant the layer that
actually terminates every public request was invisible to code review — and it
silently overrides decisions made in `frontend/security-headers.conf`.

| Repo copy | Server path |
|---|---|
| `fojin.conf` | `/etc/nginx/conf.d/fojin.conf` |
| `cloudflare-real-ip.conf` | `/etc/nginx/cloudflare-real-ip.conf` |

## These files are NOT deployed by anything

`deploy.sh` only touches the compose stack. Committing here makes the config
**reviewable and diffable**; it does not ship it. Applying a change is manual:

```bash
scp deploy/host-nginx/fojin.conf sg-vps:/tmp/fojin.conf
ssh sg-vps 'sudo cp /tmp/fojin.conf /etc/nginx/conf.d/fojin.conf && sudo nginx -t && sudo systemctl reload nginx'
```

Check for drift before trusting the repo copy:

```bash
ssh sg-vps 'sudo cat /etc/nginx/conf.d/fojin.conf' | diff -u deploy/host-nginx/fojin.conf - && echo "in sync"
```

The server also carries hand-made backups (`fojin.conf.bak-pre-cors`,
`.bak-realip-*`, `.bak-zerodt-*`) from before this was versioned. They are the
history this file now replaces; delete them once you trust git.

## Request chain

```
client → Cloudflare → host nginx (:80) ─┬─ /api/, /docs, /openapi.json → fojin_backend (127.0.0.1:8000 / :8001)
                                        └─ everything else            → fojin-frontend container (127.0.0.1:3000)
                                                                          └─ /api/, /share/qa/…, sitemap, SEO SSR → backend
```

**`/api/` does not pass through the frontend container.** Host nginx proxies it
straight to the two backend replicas. `frontend/nginx.conf`'s own `location
/api/` block is therefore dead for fojin.app traffic — it only matters if
something reaches the container directly.

`stream.fojin.ai` is a separate server block on :443 with its own certificate,
DNS-only (not proxied by Cloudflare), carrying `/api/chat/stream` with
buffering off.

## Client IP: verified working (2026-07-22)

`cloudflare-real-ip.conf` gives nginx 22 `set_real_ip_from` ranges plus
`real_ip_header CF-Connecting-IP`, so `$remote_addr` here is the true client.
`$proxy_add_x_forwarded_for` then appends it, and `app/core/client_ip.py` reads
the **last** XFF entry — which lines up.

Confirmed empirically, not just by reading the config: a request from a known
public IP produced `ratelimit:<that IP>:<window>` in Redis, and live
`chat:anon:*` keys hold varied real IPv4/IPv6 client addresses rather than one
shared bucket. The anonymous chat quota and the per-IP rate limits are genuinely
per-client.

**Known nit:** routes served *through* the frontend container (SEO/SSR — the
sitemap, `/share/qa/{id}`, `/texts/{id}`) get one more hop, so the last XFF
entry becomes the container-visible source (`10.255.1.1`) and they all share a
single rate-limit bucket. None of them are in `STRICT_PATHS` and all are cheap
public reads, so this is an availability nit (a crawler burst could 429 them for
everyone), not an auth issue. Fixing it means adding `set_real_ip_from` +
`real_ip_header X-Forwarded-For` inside `frontend/nginx.conf` too.

**Maintenance:** the Cloudflare ranges are a snapshot taken 2026-07-06. If
Cloudflare adds an edge range, requests through it stop being rewritten and fall
back to the edge IP. Re-fetch periodically from <https://www.cloudflare.com/ips/>.

## Known conflicts with the containerised config

1. **`X-Frame-Options`.** This file sets `SAMEORIGIN` (lines 42, 69);
   `frontend/security-headers.conf` sets `DENY`. Responses that pass through
   both carry two conflicting values, which is invalid — Chrome drops the header
   entirely, leaving no clickjacking protection. The durable fix lives in the
   repo: `frame-ancestors 'none'` in the CSP, which cannot be voided by a
   duplicate header from another layer. Ideally this file stops setting XFO at
   all.

2. **CORS on `/api/` (lines 65-66).** `Access-Control-Allow-Origin: *` is added
   unconditionally, on top of FastAPI's own env-driven origin allowlist. Two
   `Access-Control-Allow-Methods` headers on a preflight is the visible symptom.
   It is currently fail-safe (browsers reject `*` together with credentials) but
   it means the app's CORS policy is not the one actually served.

3. **`stream.fojin.ai` preflight (lines 118-125)** reflects `$http_origin` with
   `Access-Control-Allow-Credentials: true`, i.e. it approves preflight for *any*
   origin. Harmless today because auth is a `Authorization: Bearer` header from
   localStorage, which browsers never attach cross-origin on their own — but it
   becomes a real CSRF hole the moment auth moves to cookies.

4. `X-XSS-Protection: 1; mode=block` (lines 44, 71) is deprecated; modern
   guidance is `0`, since the legacy auditor it enables has itself been a source
   of vulnerabilities.
