# FoJin SEO 站长平台接入指南

> P0 SEO 工程层（A/B/C/D）已实施完毕（PR feat/p0-seo-pack）。本文档说明剩余必须由站长本人完成的 1 类操作：站长平台验证 + sitemap 提交。

## 1. Google Search Console（必做，5 分钟）

1. 打开 https://search.google.com/search-console
2. 选 **Domain property** → 输入 `fojin.app`
3. 复制 TXT verification record（例 `google-site-verification=xxxxxxxxxxxx`）
4. 在 Cloudflare DNS 控制台为 `fojin.app` 加这条 TXT 记录，TTL 1 分钟
5. 等 30 秒 → 回 GSC 点 **Verify**
6. **提交 sitemap**：左侧 Sitemaps → 输入 `https://fojin.app/sitemap.xml` → Submit
7. URL Inspection → 抓几条样本（`/`、`/texts/1`、`/persons/1`、`/sutras/heart-sutra`）→ 点 "Request indexing"

预期：48 小时内 GSC 开始报 impressions；2 周内 ~5 万页进入索引。

## 2. Bing Webmaster Tools（2 分钟，导入 GSC）

1. 打开 https://www.bing.com/webmasters
2. 选 **Import from GSC**（一键完成 verify + sitemap 提交）

## 3. 百度站长平台（可选，需 ICP 备案）

`.app` 顶级域无 ICP 不能在百度站长正常验证。三种方案：

- **方案 A（推荐先观望）**：当前不接入百度，依赖 Bing/Google 即可覆盖 70%+ 中文佛教用户搜索需求
- **方案 B**：注册 `fojin.cn` 或 `fojin.com.cn` 镜像域名 → 走 ICP 备案 → 301 不做（保 SEO 权重在主域）+ 用 canonical 让百度回到 `fojin.app`
- **方案 C**：先用神马搜索（阿里系，无需 ICP）：https://zhanzhang.sm.cn

## 4. HTML verification file 备选路径

如果 DNS TXT 不方便，GSC/Bing 也接受根目录放 `google[hash].html` / `BingSiteAuth.xml`：

1. 把验证文件放到 `frontend/public/` 目录
2. `git add frontend/public/google*.html`
3. 部署 → nginx 自动从 `/usr/share/nginx/html` 提供

无需改 nginx 配置，因为 `frontend/public/` 内容会被 vite build 直接 copy 到 dist/，由 nginx 默认 `try_files $uri $uri/ /index.html` 服务。

## 5. ⚠️ Cloudflare Bot Fight Mode 必查

测试发现：直查 nginx，Googlebot UA 拿到 12k 字节富内容 ✅；但走 Cloudflare（fojin.app）只拿到 2.4k 精简版 ❌。**这是 Cloudflare Bot Fight Mode 在拦截/降级 Googlebot 流量**——属于 CF 的 over-protection。

修复（必做）：

1. Cloudflare Dashboard → 选择 fojin.app → **Security → Bots**
2. **Bot Fight Mode** 设为 **Off**（或保留 Off，不要开 Super Bot Fight Mode）
3. 或者添加 WAF Custom Rule：`User-Agent contains "Googlebot" or "Bingbot" or "Baiduspider"` → Action: **Skip**（跳过所有 security feature）

**未做这步前，所有上面的 SEO 工作对 Google 都是无效的**——因为 Google 看到的是 CF 精简版，不是 nginx 实际返回。

验证：
```bash
curl -s -A "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" https://fojin.app/texts/1 | wc -c
# 应该 ≥ 12000；若 ≈ 2400 表示 CF 仍在拦截
```

## 6. 验证当前 SEO 改动是否生效

```bash
# 经文 detail 页应该有 noscript 内的正文片段 + breadcrumb
curl -s https://fojin.app/texts/1 | grep -E 'noscript|BreadcrumbList' | head -3

# 人物 SEO 页应该返回真实 HTML，不是 SPA shell
curl -s https://fojin.app/persons/1 | grep -E '<title|<h1>|application/ld\+json' | head -5

# Sitemap 应该包含 persons 分片
curl -s https://fojin.app/sitemap.xml | grep persons

# Googlebot UA 看到的内容应该 ≥ 真人浏览器
curl -s -A "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" https://fojin.app/texts/1 | wc -c
```

## 7. 监控指标（6 周回访）

| 指标 | 当前 baseline | 目标（6 周） |
|---|---|---|
| GSC indexed pages | ~10–100（推测） | ≥ 30,000 |
| 月自然搜索点击 | < 100（推测） | ≥ 5,000 |
| 收录的 person 页面 | 0 | ≥ 20,000 |
| 富结果（Book / Person / Breadcrumb） | 0 | ≥ 1,000 impressions |

回访时检查 GSC → Performance + Pages → Indexed。
