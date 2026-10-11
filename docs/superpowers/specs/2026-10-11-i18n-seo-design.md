# 多语言可收录（繁体 / 英文 SEO）设计

日期：2026-10-11
状态：已定稿，待实施
分支：`feat/i18n-seo`

## 1. 目标

让繁体中文版、英文版的 fojin 页面**能被搜索引擎单独收录**，从而让港台新马与海外华人通过搜索找到 fojin。

这是「全球增长」的子项目 ①（用户 2026-10-11 拍板：目标人群 = 全球华语佛教徒；路线 = 搜索先行 → 核对页 → 首页承接 → 渠道）。

**不做**：路径前缀（`/zh-Hant/…`）、子域、新语种、翻译经文正文（正文就是原典）、Search Console 操作（要用户账号，上线后由用户提交 sitemap）、**辞典页与人物页的多语版本**（见 §2.1）、百度（另立子项目，需用户提供站长平台主动推送 token）。

## 2. 关键事实（实测，2026-10-11，origin/master `cf81006`）

| 事实 | 数值 / 现象 | 来源 |
|---|---|---|
| 周访问 | 13 周持平在 600–700 | Umami |
| 30 天访问：CN / US / SG / HK / JP / TW | 1,652 / 266 / 146 / 138 / 91 / 64 | Umami |
| 30 天搜索来源：Bing / 百度 / Google | 89 / 69 / 43 | Umami referrer |
| UI 翻译 | zh / zh-Hant / en 各 1,623 键，硬编码中文 ratchet 基线为空 | `public/locales`、`i18n-baseline.json` |
| Googlebot 抓 `/?lang=en` | `<html lang="zh-CN">` + 简体标题 + canonical `https://fojin.app/` | curl |
| 服务端 hreflang | **无**（仅 7 个页面运行时 Helmet 有，且 canonical 指回简体版，自相矛盾） | 代码 + curl |
| 经名存储 | 繁体（CBETA 原样），简体页模板却是简体 → 简体页标题是繁体经名 | `seo.py`、`title_zh` |
| 预渲染 Worker `fojin-prerender` | **路由未生效**：Googlebot 与浏览器拿到同一份 12.7 KB 后端 SSR | curl `/texts/235` 两种 UA |
| `/collections/:id`（13 个）、`/cross-canon` | 在 sitemap 里，但服务端 canonical 是 `/` | Explore 报告 |
| robots.txt | `Disallow: /search?` 挡住了 `/search?lang=…` 这个现有 hreflang 目标 | `public/robots.txt` |

### 2.1 实施前再评估（2026-10-11，生产 host nginx 日志 7 天）

| 事实 | 数值 |
|---|---|
| Googlebot 抓取 | 4,386 次 ≈ 630/天（8 月为 287/7 天） |
| 其中 `/dict/*` / `/texts/*` / `/persons/*` | 3,230（74%）/ 401 / 295 |
| Googlebot 已在抓 `?lang=` URL | 18 次（如 `/?lang=en`、`/sutras/diamond-sutra?lang=en`），全部拿到简体页 → 被合并，白费 |
| 真 Baiduspider | ≈ 0（带该 UA 的多为漏洞扫描：`/.env`、`/proc/self/environ`） |

据此收窄：辞典约 30 万词条、人物约 4.4 万，正文是中文辞典内容，换语言只换外壳 → 三语化会新增约 70 万个近似重复 URL，稀释 Google 现在花在辞典上的 74% 抓取。**本期只做有真翻译价值的页面**（首页、静态 shell、专题、经典导读、经文页约 1 万部）；辞典 / 人物只修正 `<html lang>`，不加语言版本、不输出 hreflang。

## 3. 方案：沿用 `?lang=` 作为独立 URL（方案 A）

三种语言版本的 URL：

| 语言 | URL | hreflang |
|---|---|---|
| 简体（默认） | `https://fojin.app/texts/235` | `zh-Hans`，同时作 `x-default` |
| 繁体 | `https://fojin.app/texts/235?lang=zh-Hant` | `zh-Hant` |
| 英文 | `https://fojin.app/texts/235?lang=en` | `en` |

每个版本：`<html lang>` 与 `og:locale` 对应该语言；title / description 用该语言模板；**canonical 指向自己**（含 `?lang`）；服务端输出全部三条 hreflang + x-default。

`lang` 只认 `zh-Hant`、`en` 两个值（不区分大小写，与 nginx `map` 的字符串匹配一致；canonical 一律写规范形式，大小写变体因此归并）；其他值（含 `zh`）一律按简体处理，canonical 指回无参数 URL，**不产生新的 URL 空间**。

选 A 不选路径前缀的理由：改动集中在服务端出口，URL 结构与已有 hreflang 测试不变；Google 官方支持参数区分语言。8 周后若收录信号不足再升级为路径前缀，A 的服务端工作可复用。

## 4. 组件

### 4.1 共享的语言工具（前后端各一份，行为对齐）

- 后端 `backend/app/services/seo_lang.py`（新）：
  - `resolve_lang(request) -> "zh" | "zh-Hant" | "en"`
  - `lang_url(path, lang)`：zh 返回无参 URL，其他附 `?lang=`；只拼路径与 lang，不携带其他查询参数（与现有 canonical 丢弃查询串的规则一致）
  - `hreflang_links(path) -> str`：四条 `<link rel="alternate" hreflang=…>`
  - `html_lang(lang)`：`zh-Hans` / `zh-Hant` / `en`；`og_locale(lang)`：`zh_CN` / `zh_TW` / `en_US`
  - `localize_title(title_zh, lang)`：zh → 简繁并列「简体（繁體）」（两者相同时只写一次；不直接替换，避免已收录的 1 万多页标题突变引起排名波动）；zh-Hant → 原样（库内本是繁体）；en → 原样
- 前端 `frontend/src/seo/langUrl.ts`（新）：`langUrl(path, lng)`、`hreflangLinks(path)`，供所有 Helmet 使用。

### 4.2 服务端出口

| 出口 | 改动 |
|---|---|
| 根 shell `index.html` + 静态 shell（`seoPages()` 插件） | 构建期为每个路由多产出 `index.zh-Hant.html`、`index.en.html`；首页另出专用 shell（`_home/`，含 hreflang），通用 SPA 兜底只换语言不加 hreflang（它服务所有未预构建路由）；专题详情 13 个与 `/cross-canon` 新增 shell 以修正其 canonical；文案取自 `staticPages.json` 新增的 `zh-Hant`/`en` 分支；替换 `<html lang>`、`og:locale`、根 JSON-LD `inLanguage`、canonical、hreflang |
| `frontend/nginx.conf` | 顶层加 `map $arg_lang $lang_sfx { "zh-Hant" ".zh-Hant"; "en" ".en"; default ""; }`；静态 shell 与 SPA 兜底改为 `try_files …/index$lang_sfx.html …/index.html` |
| `backend/app/api/seo.py`（经文详情页；分享页 `/share/qa` 与 noindex 的 `/read` 页不分语言） | 取对应语言的 shell（`index$lang_sfx.html`）；模板文案三语化；`localize_title`；canonical / hreflang / `html lang` / og:locale 按语言 |
| `seo_dict.py`、`seo_persons.py`（全 SSR） | **仅**把 `<html lang>` 从 `zh-Hans` 修为与内容一致的值；不加语言版本、不加 hreflang（§2.1） |
| `backend/app/api/sitemap.py` | 加 `xmlns:xhtml`，static 与 texts 两类 sitemap 的每个 `<url>` 带三语 `xhtml:link`（texts 约 1 万条，远低于单文件上限）；dict / persons sitemap 不变 |

### 4.3 运行时（Googlebot 会执行 JS，必须与服务端一致）

- 所有已有 Helmet canonical 的页面改用 `langUrl(path, currentUILang())`，hreflang 改用 `hreflangLinks`。简体的 hreflang 值由现在的 `zh` 改为 `zh-Hans`（更精确，避免繁体用户被分到简体页），相应测试断言同步更新。
- Helmet title 中的经名走 `localizeHan`（已有工具），与服务端 `localize_title` 一致。
- 语言切换器（`Layout.tsx`）在 `changeLanguage` 后用 `history.replaceState` 写入 / 去掉 `?lang=`，让分享出去的链接带着语言。

### 4.4 顺手修

- `/collections/:id`、`/cross-canon` 的服务端 canonical 改为自身路径（nginx 精确 location 或 shell 构建，按实施时最小改动选）。
- 搜索页从 hreflang 中移除（它被 robots 挡、且结果页不该收录），robots.txt 不动。
- `workers/prerender/README` 注明「路由未生效，勿部署」，代码不动。

## 5. 数据流

```
爬虫 → Cloudflare（HTML 不缓存，cf-cache-status: DYNAMIC）→ host nginx → 前端 nginx
   ├─ 静态 shell / SPA 兜底：map $arg_lang → index{.lang}.html
   └─ /texts/:id、/share/qa/*、sitemap → 后端 resolve_lang(request) → 对应语言的 head（/dict、/persons 不分语言）
浏览器 → 同上拿到对应语言 shell → React 起来后 i18n 按 ?lang 选语言 → Helmet 输出同一套 canonical/hreflang
```

## 6. 错误处理

- 未知 `lang` 值：按简体处理，canonical 回无参 URL（防止 `?lang=xyz` 被当成新页面）。
- 对应语言 shell 缺失（构建异常）：nginx `try_files` 回落到简体 shell；后端取 shell 失败沿用现有回落逻辑。
- OpenCC t2s 失败：原样输出标题，记 warning。

## 7. 测试与验收

- 后端：`seo_lang` 单测；`seo.py` / sitemap 按三语各断言 `html lang`、title、canonical、hreflang；`seo_dict` / `seo_persons` 只断言 `html lang`；**所有新断言先在未改代码上跑红**。
- 前端：`langUrl` 单测；更新已有 7 个页面的 hreflang 断言（`?lang=` 值不变，新增 canonical 带语言的断言）；`seoPages()` 产出三语 shell 的测试。
- 现有 SEO 测试全部保持绿（清单见实施计划）。
- nginx：`nginx -t` + 本地 compose 起服务后 curl 三语 × 五类页面。
- **上线后实测**：脚本用 Googlebot / Baiduspider UA 抓 3 语 × 首页 / 静态 shell / 专题 / 经文页，外加辞典与人物页各一，逐项核对 lang / title / canonical / hreflang；用浏览器真机切换语言看 URL 写入。
- 成功判据（8 周，用户在 Search Console 查看）：zh-Hant 与 en 页面出现在「已编入索引」；港台新马搜索来源访问较基线（30 天 HK 138 / TW 64 / SG 146）上升。
