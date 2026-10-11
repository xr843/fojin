# fojin-prerender（休眠中，勿部署）

> ⚠️ **2026-10-11 实测：这个 Worker 的路由没有生效。** 用 Googlebot UA 与普通浏览器 UA 抓
> `https://fojin.app/texts/235`，拿到的是同一份约 12.7 KB 的后端 SSR（`backend/app/api/seo.py`），
> 不是本 Worker 渲染的精简页。
>
> 它只输出简体、`<html lang="zh-CN">`、不认 `?lang=`，与多语言 SEO
> （`docs/superpowers/specs/2026-10-11-i18n-seo-design.md`）冲突。**重新部署会让 Googlebot 在
> `/texts/*` 上拿到退化且不分语言的页面。** 经文页的爬虫 HTML 由后端负责。

代码保留仅供参考；要删除它，连同 `wrangler.toml` 与 CI 里的类型检查一起删。
