#!/usr/bin/env bash
# 本地验收：用真实 frontend/nginx.conf + dist/ 起一个非 root 的 nginx，按 ?lang= 抓各类 shell。
#
# 用法：cd frontend && npm run build && bash scripts/nginx-lang-check.sh
# 需要本机有 nginx 可执行文件（不需要 root、不需要 docker）。CI 不跑它；改 nginx.conf
# 或 src/seo/buildShells.ts 后、上线前手动跑一次。见
# docs/superpowers/specs/2026-10-11-i18n-seo-design.md。
set -euo pipefail
cd "$(dirname "$0")/.."
FRONTEND=$PWD
PORT=${PORT:-18080}
WORK=$(mktemp -d)
trap 'nginx -p "$WORK" -c "$WORK/nginx.conf" -s stop 2>/dev/null || true; rm -rf "$WORK"' EXIT

[ -f dist/index.html ] || { echo "dist/ 不存在，先 npm run build"; exit 2; }

# 生产里这份 conf 是 conf.d/default.conf（http 上下文）；这里包一层 http{}，
# 并把端口、security-headers 的绝对路径换成本地的。
sed -e "s#listen 80;#listen $PORT;#" \
    -e "s#/etc/nginx/security-headers.conf#$FRONTEND/security-headers.conf#g" \
    -e "s#/etc/nginx/html-no-cache.conf#$WORK/html-no-cache.conf#g" \
    -e "s#root /usr/share/nginx/html;#root $FRONTEND/dist;#" \
    nginx.conf > "$WORK/site.conf"
sed -e "s#/etc/nginx/security-headers.conf#$FRONTEND/security-headers.conf#g" html-no-cache.conf > "$WORK/html-no-cache.conf"
mkdir -p "$WORK/logs"
cat > "$WORK/nginx.conf" <<EOF
pid $WORK/nginx.pid;
error_log $WORK/logs/error.log;
events {}
http {
  include /etc/nginx/mime.types;
  access_log off;
  client_body_temp_path $WORK/body;
  proxy_temp_path $WORK/proxy;
  fastcgi_temp_path $WORK/fastcgi;
  uwsgi_temp_path $WORK/uwsgi;
  scgi_temp_path $WORK/scgi;
  include $WORK/site.conf;
}
EOF
nginx -p "$WORK" -c "$WORK/nginx.conf" -t
nginx -p "$WORK" -c "$WORK/nginx.conf"

fail=0
check() { # path expected-substring
  local body
  body=$(curl -s "http://127.0.0.1:$PORT$1")
  if grep -qF -- "$2" <<<"$body"; then echo "ok   $1  ⊃ $2"; else echo "FAIL $1  ⊅ $2"; fail=1; fi
}
code() { # path expected-status
  local got
  got=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT$1")
  if [ "$got" = "$2" ]; then echo "ok   $1  → $2"; else echo "FAIL $1  → $got (want $2)"; fail=1; fi
}

check "/"                                '<html lang="zh-Hans">'
check "/"                                'hreflang="zh-Hant" href="https://fojin.app/?lang=zh-Hant"'
check "/?lang=zh-Hant"                   '<html lang="zh-Hant">'
check "/?lang=en"                        '<link rel="canonical" href="https://fojin.app/?lang=en"'
check "/chat"                            '<link rel="canonical" href="https://fojin.app/chat"'
check "/chat?lang=en"                    '<html lang="en">'
check "/chat?lang=xyz"                   '<html lang="zh-Hans">'
check "/search?lang=zh-Hant"             '<html lang="zh-Hant">'
check "/sutras/heart-sutra?lang=zh-Hant" '<link rel="canonical" href="https://fojin.app/sutras/heart-sutra?lang=zh-Hant"'
check "/collections/huayan"              '<link rel="canonical" href="https://fojin.app/collections/huayan"'
check "/collections/huayan?lang=en"      'Avatamsaka'
check "/cross-canon?lang=en"             '<html lang="en">'
check "/map?lang=en"                     '<html lang="en">'
check "/map"                             '<html lang="zh-Hans">'
code  "/chat"                            200
code  "/cross-canon"                     200
code  "/collections/huayan"              200
code  "/CROSS-CANON"                     301
code  "/_home/index.html"                404
nocache() { # path — the SPA/home shells reference hashed bundles and must never be cached
  if curl -sI "http://127.0.0.1:$PORT$1" | grep -qi '^cache-control: no-cache'; then echo "ok   $1  no-cache"; else echo "FAIL $1  missing no-cache"; fail=1; fi
}
nocache "/"
nocache "/?lang=en"
nocache "/map"
nocache "/map?lang=zh-Hant"
nocache "/chat?lang=en"
nocache "/sutras/heart-sutra"
nocache "/collections/huayan"
nocache "/collections/no-such-series"
nocache "/cross-canon?lang=zh-Hant"
redirect() { # path expected-Location
  local got
  got=$(curl -sI "http://127.0.0.1:$PORT$1" | tr -d '\r' | awk 'tolower($1)=="location:"{print $2}')
  if [ "$got" = "$2" ]; then echo "ok   $1  ↦ $2"; else echo "FAIL $1  ↦ $got (want $2)"; fail=1; fi
}
redirect "/CROSS-canon?lang=en"          "/cross-canon?lang=en"
redirect "/CHAT"                         "/chat"
code  "/collections/no-such-series"      200
code  "/assets/does-not-exist.js"        404  # unchanged from master: a missing bundle must not get an HTML shell
exit $fail
