FROM node:22-alpine AS build

# Opt-in Umami analytics. Both must be set for the tracking script to be
# injected at runtime; see frontend/src/umami.ts.
ARG VITE_UMAMI_URL=""
ARG VITE_UMAMI_WEBSITE_ID=""
ENV VITE_UMAMI_URL=$VITE_UMAMI_URL
ENV VITE_UMAMI_WEBSITE_ID=$VITE_UMAMI_WEBSITE_ID

WORKDIR /app
COPY package.json package-lock.json* ./
# 生产 VPS 到 npm 源的链路时好时坏（2026-10-04 单次元数据请求 12-13 s，
# 连续两次部署死在 ECONNRESET），默认 2 次重试撑不住。加大重试与退避，
# 并关掉 audit/fund 两次额外的网络往返。
RUN npm install --fetch-retries=6 --fetch-retry-mintimeout=20000 \
    --fetch-retry-maxtimeout=180000 --no-audit --no-fund
COPY . .
RUN npm run build

# Pre-compress static assets for gzip_static
RUN find dist -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.svg' -o -name '*.json' \) \
    -exec gzip -9 -k {} \;

FROM nginx:stable-bookworm
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/security-headers.conf

# Run as non-root nginx user
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid
USER nginx

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
