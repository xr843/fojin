# Umami Analytics Integration Design

**Date:** 2026-03-30
**Status:** Approved

## Goal

Integrate Umami self-hosted analytics into fojin to understand user behavior — who visits, what they use, which texts they read. Zero external tracking, privacy-first.

## Architecture

```
Browser
  ├── Umami JS (auto: pageviews, country, device, referrer)
  └── umami.track() custom events (search, chat, read)
        ↓
  nginx /umami → Umami service (port 3001, internal)
        ↓
  PostgreSQL (shared fojin instance, Umami manages its own tables)
```

## Changes

### 1. docker-compose.yml — Add Umami service

```yaml
umami:
  image: ghcr.io/umami-software/umami:postgresql-latest
  container_name: fojin-umami
  restart: always
  logging: *default-logging
  mem_limit: 256m
  cpus: 0.5
  environment:
    DATABASE_URL: postgresql://${POSTGRES_USER:-fojin}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-fojin}
    APP_SECRET: ${UMAMI_APP_SECRET:-change-me-in-production}
    BASE_PATH: /umami
  ports:
    - "127.0.0.1:3001:3000"
  depends_on:
    postgres:
      condition: service_healthy
  healthcheck:
    test: ["CMD-SHELL", "wget -q --spider http://localhost:3000/umami/api/heartbeat || exit 1"]
    interval: 10s
    timeout: 5s
    retries: 5
```

### 2. .env.example — Add Umami secret

```env
# Umami Analytics
UMAMI_APP_SECRET=change-me-generate-a-random-secret
```

### 3. frontend/nginx.conf — Add /umami reverse proxy

```nginx
# Umami Analytics
location /umami {
    proxy_pass http://umami:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### 4. frontend/index.html — Add tracking script

```html
<!-- Umami Analytics (privacy-first, no cookies) -->
<script defer src="/umami/script.js" data-website-id="WEBSITE_ID"></script>
```

Note: `WEBSITE_ID` is generated after first Umami login. This will be a manual step after deployment.

### 5. Custom Event Tracking

#### Search — `frontend/src/pages/search/` (on search execute)

```typescript
if (typeof umami !== 'undefined') {
  umami.track('search', { keyword: query, results: resultCount })
}
```

#### AI Chat — `frontend/src/pages/chat/` (on message send)

```typescript
if (typeof umami !== 'undefined') {
  umami.track('chat', { question: message.slice(0, 30) })
}
```

#### Text Reading — `frontend/src/pages/text/` (on page mount)

```typescript
if (typeof umami !== 'undefined') {
  umami.track('read', { id: textId, title: textTitle })
}
```

## Access

- Dashboard: `https://fojin.app/umami`
- Default login: `admin` / set password on first login
- Only authenticated users can view analytics data

## Privacy

- No cookies, no fingerprinting
- AI chat questions truncated to 30 characters
- All data stored on own server (PostgreSQL)
- Umami is GDPR/CCPA compliant by design

## Post-Deployment Steps

1. Visit `https://fojin.app/umami`, login with `admin`/`umami`
2. Change admin password
3. Add website: name=fojin, domain=fojin.app
4. Copy the generated Website ID
5. Update `index.html` `data-website-id` attribute with the ID
6. Redeploy frontend

## Future Extensions

- Query Umami's `website_event` table directly via SQL for advanced aggregation (search keyword ranking, reading heatmap)
- Add more custom events (knowledge graph interactions, registration funnel) as needed
