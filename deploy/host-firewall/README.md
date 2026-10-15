# host-firewall — 80 端口只放行 Cloudflare

sg-vps 上的宿主 nginx 在 `:80` 接 fojin.app / mcp.fojin.ai / analytics.fojin.app / fojin.ai，
这些域名都经 Cloudflare 代理。但 `stream.fojin.ai` 是 DNS-only，它的 A 记录就是源站 IP，
任何人都能带 `Host: fojin.app` 直连 `:80`，绕过 Cloudflare 的 WAF、限流和防爬规则
（2026-10-15 从 la-vps 实测直连返回 200）。

本目录的文件把 `:80` 限制为 Cloudflare 官方 IP 段 + 本机/内网/Tailscale。
**443 不动**（stream.fojin.ai 的 SSE 由浏览器直连）；SSH 不动。

| 本目录 | 服务器上的位置 |
|---|---|
| `fojin-cf-firewall.sh` | `/usr/local/sbin/fojin-cf-firewall.sh` |
| `fojin-cf-firewall.service` / `.timer` | `/etc/systemd/system/`（开机 + 每周刷新 IP 段） |
| `certbot-pre-fojin-open-80.sh` | `/etc/letsencrypt/renewal-hooks/pre/fojin-open-80.sh` |
| `certbot-post-fojin-close-80.sh` | `/etc/letsencrypt/renewal-hooks/post/fojin-close-80.sh` |

和 `deploy/host-nginx/` 一样，**不由 deploy.sh 部署**，改动需手工同步到服务器。

## 为什么要 certbot 钩子

stream.fojin.ai 的证书用 HTTP-01 在 `:80` 验证，Let's Encrypt 是直连源站、不经 Cloudflare。
钩子在续期前放开、续期后收回；只有真正要续期时才运行，窗口约 15 秒
（2026-10-15 `certbot renew --dry-run` 验证通过）。

## 常用操作

```bash
sudo /usr/local/sbin/fojin-cf-firewall.sh status   # 看规则
sudo /usr/local/sbin/fojin-cf-firewall.sh remove   # 紧急撤销（80 对所有人开放）
sudo /usr/local/sbin/fojin-cf-firewall.sh apply    # 重新应用
```

验证：从别的机器 `curl -H 'Host: fojin.app' http://<源站IP>/api/health` 应超时；
`curl https://fojin.app/api/health` 应 200。
