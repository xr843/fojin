#!/bin/bash
# fojin-cf-firewall — only Cloudflare may reach this host's port 80.
#
# Why: fojin.app / mcp.fojin.ai / analytics.fojin.app / fojin.ai are proxied by
# Cloudflare and terminate on host nginx :80. Without this, anyone who learns
# the origin IP (stream.fojin.ai is DNS-only, so its A record IS the origin IP)
# can send `Host: fojin.app` straight to :80 and skip Cloudflare's WAF, rate
# limiting and bot rules. Verified 2026-10-15 from la-vps: direct request → 200.
#
# Scope: port 80 only. 443 is left alone on purpose — stream.fojin.ai (AI chat
# SSE) is served there directly to browsers. SSH/Tailscale are not touched.
#
#   apply    rebuild the allowlist from Cloudflare's published ranges (cached)
#   remove   drop the restriction entirely (used by the certbot pre-hook, and
#            as the emergency rollback)
#   status   show the current rules
set -euo pipefail

CHAIN=FOJIN-HTTP
CACHE=/etc/fojin-cf-ips-v4.txt
CF_URL=https://www.cloudflare.com/ips-v4
# Loopback is matched by `-i lo`; these cover docker bridges, the VPC and Tailscale.
PRIVATE="10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10"

log() { echo "[$(date '+%F %T')] fojin-cf-firewall: $*"; }

valid_list() { # a usable list: >= 10 lines, every line an IPv4 CIDR
  [ "$(grep -c . "$1")" -ge 10 ] && ! grep -qvE '^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$' "$1"
}

refresh_cache() {
  local tmp; tmp=$(mktemp)
  if curl -fsS --max-time 20 "$CF_URL" | tr -d '\r' | grep . > "$tmp" && valid_list "$tmp"; then
    if ! cmp -s "$tmp" "$CACHE" 2>/dev/null; then
      install -m 644 "$tmp" "$CACHE"; log "Cloudflare range list updated ($(wc -l < "$CACHE") ranges)"
    fi
  else
    log "WARNING: could not fetch $CF_URL, using cached list"
  fi
  rm -f "$tmp"
}

remove_jumps() {
  while iptables -C INPUT -p tcp --dport 80 -j "$1" 2>/dev/null; do
    iptables -D INPUT -p tcp --dport 80 -j "$1"
  done
}

drop_chain() {
  iptables -L "$1" -n >/dev/null 2>&1 || return 0
  remove_jumps "$1"; iptables -F "$1"; iptables -X "$1"
}

apply() {
  refresh_cache
  if [ ! -s "$CACHE" ] || ! valid_list "$CACHE"; then
    log "ERROR: no valid Cloudflare range list — refusing to restrict port 80"; exit 1
  fi
  # Build the new chain fully, then swap the INPUT jump, so port 80 is never
  # half-configured while traffic is flowing.
  local new="${CHAIN}-NEW"
  drop_chain "$new"
  iptables -N "$new"
  iptables -A "$new" -i lo -j ACCEPT
  for c in $PRIVATE $(cat "$CACHE"); do iptables -A "$new" -s "$c" -j ACCEPT; done
  iptables -A "$new" -j DROP
  iptables -I INPUT 1 -p tcp --dport 80 -j "$new"
  drop_chain "$CHAIN"
  iptables -E "$new" "$CHAIN"
  log "applied: port 80 restricted to $(wc -l < "$CACHE") Cloudflare ranges + local/private"
}

case "${1:-}" in
  apply)  apply ;;
  remove) drop_chain "${CHAIN}-NEW"; drop_chain "$CHAIN"; log "removed: port 80 open to everyone" ;;
  status) iptables -S INPUT | grep -- "--dport 80" || echo "(no port-80 jump)"; iptables -S "$CHAIN" 2>/dev/null | head -5; echo "..."; iptables -S "$CHAIN" 2>/dev/null | tail -2 ;;
  *) echo "usage: $0 apply|remove|status" >&2; exit 2 ;;
esac
