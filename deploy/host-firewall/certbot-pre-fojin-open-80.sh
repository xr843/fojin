#!/bin/bash
# stream.fojin.ai renews via HTTP-01 on :80, which Let's Encrypt reaches directly (not via Cloudflare).
/usr/local/sbin/fojin-cf-firewall.sh remove
