# FoJin 安全与性能审计报告

**仓库**：https://github.com/xr843/fojin
**HEAD**：`2dddfa3cb3ee8fa7c56b6d77d3e799932d8abfd4`
**审计日期**：2026-05-08
**审计员**：Claude Opus 4.7（主审）+ 工具链（gitleaks 8.18 / pip-audit 2.10 / semgrep 1.162 / bandit / npm audit）
**目标 URL**：https://fojin.app/（生产）

---

## 摘要

| 等级 | 数量 | 说明 |
|------|------|------|
| **P0** | 1 | 立即修复（已部署到生产） |
| **P1** | 5 | 1-2 周内修复 |
| **P2** | 6 | 1 月内修复或可接受 |
| **P3 / 误报** | 8 | 已确认无影响 |

**总体评估**：项目工程纪律相当好——非 root 容器、参数化 SQL、DOMPurify 严格白名单、defusedxml、CSP/HSTS/XFO/PP 全套安全头、CI 已集成 bandit + pip-audit + npm audit、Pydantic/SQLAlchemy 使用规范。**主要风险集中在两点**：(1) 用户 BYOK API key 加密派生方式偏弱；(2) 反代信任边界处理不当（XFF 取首位可被伪造）。无供应链型 RCE，无未鉴权敏感接口。

---

## P0 — 立即修复

### P0-1：BYOK API key 加密强度不足（KDF 缺失）
- **位置**：`backend/app/core/crypto.py:11-14`
- **证据**：
  ```python
  def _get_fernet() -> Fernet:
      key = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
      return Fernet(base64.urlsafe_b64encode(key))
  ```
- **问题**：用户 BYOK 的 LLM API key（OpenAI/Anthropic/DeepSeek 等付费 token）入库前用 Fernet 加密，但 Fernet 密钥由 **JWT_SECRET_KEY** 单轮 SHA256 派生，无 salt、无 KDF。问题：
  1. 加密密钥与认证密钥混用——一旦 JWT secret 因日志/堆栈/备份泄露，攻击者可解密所有用户 API key（金钱损失直接发生）。
  2. 单轮 SHA256 不是 KDF；若 JWT secret 是低熵字符串（如部署时手输的短串），离线爆破成本极低。
  3. 同一 KEY 同一密文可枚举对比识别。
- **CWE**：CWE-326（Inadequate Encryption Strength）+ CWE-916（Use of Password Hash With Insufficient Computational Effort）
- **修复**：
  - 引入独立 `API_KEY_ENCRYPTION_KEY` 环境变量（32+ 随机字节，base64），不要复用 JWT secret。
  - 用 `cryptography.hazmat.primitives.kdf.hkdf.HKDF` 派生（带 salt）；或直接用 `Fernet.generate_key()` 生成的强 key。
  - 迁移：在 user 表加 `api_key_kdf_version` 字段，旧记录标记 v1（旧派生），新记录写 v2，启动时一次性 re-encrypt 旧记录。
- **不可降级**：需 codex 复核迁移路径。

---

## P1 — 一到两周内修复

### P1-1：git history 中残留旧 Amap key 明文
- **位置**：`backend/scripts/fetch_amap_temples.py`、`fetch_amap_temples_v2.py`、`fetch_amap_temples_v3.py`、`backfill_address_regeo.py`（commit `11a9833c` `4d400efa` `4d4f13ff` `17f7a3e3`）
- **证据**：
  ```
  $ git log --all -p -- backend/scripts/fetch_amap_temples.py | grep KEY=
  +AMAP_KEY = "7971e9b134c4684c3b43b6e442475d0e"
  ```
  另含 frontend MapTiler key 历史泄露：`frontend/src/components/kg-map/DeckGLMap.tsx:31` 现行代码仍硬编码 `MAPTILER_KEY = "sBS5GCqJuftwymqkp64I"`。
- **问题**：现行代码已 redact 为 `os.environ.get("AMAP_KEY")`，但 `git log -p` / GitHub 网页可直接拉到旧 SHA 对应 key。memory 记录该 key 已绑定 IP 白名单缓解，但白名单不是注销——攻击者可复用配额、消耗免费层（每天 ~100 次置信影响 V3 抓取节奏）。
- **CWE**：CWE-540（Inclusion of Sensitive Information in Source Code）
- **修复**：
  1. **Amap key**：到高德控制台彻底注销旧 key（`7971e9b134c4684c3b43b6e442475d0e`），确认所有 cron 已切到新 env-var key。
  2. **MapTiler key**：移到 env var 注入（`VITE_MAPTILER_KEY`），到 MapTiler 控制台对当前 key 加 referer 白名单（仅 `fojin.app` + `localhost`）。
  3. 不需要 git filter-repo —— 重写历史会破坏每条 commit 的认证，注销 key 是更干净的处置。

### P1-2：X-Forwarded-For 取首位可被伪造（rate-limit + audit log）
- **位置**：`backend/app/core/rate_limit.py:35-40`、间接影响 `backend/app/services/auth.py:71-130`（password audit）
- **证据**：
  ```python
  forwarded = request.headers.get("x-forwarded-for")
  if forwarded:
      client_ip = forwarded.split(",")[0].strip()  # 取首位
  ```
  nginx 配置使用 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`（**追加** 模式），意味着客户端发来的 `XFF: 1.2.3.4` 会被 nginx 拼成 `XFF: 1.2.3.4, <真实IP>`。后端取首位 → 拿到客户端伪造值。
- **问题**：
  - 攻击者轮换伪造 XFF 即可绕过基于 IP 的 rate limit（登录/注册敏感路径的 STRICT_PATHS）。
  - password audit 表 (`auth.py:98 _record_password_audit`) 写入伪造 IP，事后追责无效。这与 memory `project_fojin_password_reset_20260501.md`（id=3 admin 04-12 密码异常变更）形成关键关联——若审计表当时被污染，溯源链已断。
- **CWE**：CWE-348（Use of Less Trusted Source）+ CWE-807（Reliance on Untrusted Inputs）
- **修复**：
  - 取 `XFF` 字符串拆分后的**最后一个**条目（`$proxy_add_x_forwarded_for` 追加 nginx 自己看到的真实 IP 在末尾）；或
  - 在 uvicorn 启动加 `--proxy-headers --forwarded-allow-ips=127.0.0.1,172.16.0.0/12`，让 starlette 的 `request.client.host` 自带可信代理校验后直接使用。
- **优先级**：与 P0-1 一起修；password audit 完整性是合规底线。

### P1-3：python-multipart 依赖含 3 个已知 CVE，项目用于 FastAPI 上传
- **位置**：`backend/requirements.txt`（python-multipart 0.0.20）
- **证据**：pip-audit 输出
  - CVE-2026-24486 → fix 0.0.22
  - CVE-2026-40347 → fix 0.0.26
  - CVE-2026-42561 → fix 0.0.27
- **问题**：python-multipart 是 FastAPI 解析 `multipart/form-data` 的依赖，`/api/chat/attachments`（10MB 文件上传）走它。CVE 详情未在本次拉取中展开——但综合来看可能涉及解析 DoS / boundary 绕过。
- **修复**：升至 `python-multipart>=0.0.27`；deploy 后回归测试 `/api/chat/attachments` 上传。

### P1-4：Pillow 11.0.0 含 5 个 CVE，img/og 卡片渲染路径需关注
- **位置**：`backend/requirements.txt`（pillow 11.0.0）
- **证据**：CVE-2026-25990 / 40192 / 42308 / 42310 / 42311（fix 12.2.0）
- **问题**：Dockerfile 注释提到 Pillow 用于 `/api/og/*` 卡片图渲染（社交分享 OG image）。OG 端点接受标题/描述等用户可控字段——若未来加图片输入或字体注入，存在被利用面；现状是字符串渲染到 CJK 字体，相对安全。
- **修复**：升至 `pillow>=12.2.0`；回归测试 `/api/og/share?title=...`。

### P1-5：lxml 5.3.0 含 CVE-2026-41066
- **位置**：`backend/requirements.txt`
- **证据**：pip-audit fix 6.1.0
- **问题**：lxml 用于 TEI XML / 可能其他 XML 解析。`backend/app/core/tei_84000_parser.py` 实际用 `defusedxml.ElementTree.fromstring` 安全包装（XXE 已防御），但 lxml 直接调用点需排查。CI 已对此 CVE 加 `--ignore-vuln CVE-2026-41066`，**说明项目已知但延期**——审计角度需明确接受。
- **修复**：升至 `lxml>=6.1.0`；移除 CI ignore 列表中的对应 CVE。

---

## P2 — 一个月内修复或视情况接受

### P2-1：docker-compose 默认 JWT_SECRET_KEY 与 UMAMI_APP_SECRET 是 `change-me-in-production`
- **位置**：`docker-compose.yml:87` `:135`
- **证据**：
  ```yaml
  JWT_SECRET_KEY: ${JWT_SECRET_KEY:-changeme-in-production}
  UMAMI_APP_SECRET: ${UMAMI_APP_SECRET:-change-me-in-production}
  ```
- **缓解**：`backend/app/config.py:109` 在 `ENVIRONMENT=production` 时启动失败保护，故实际部署不会带默认值跑起来——这是真正的关键拦截。但 staging/dev 没有这层保护。
- **修复**：把 `:-changeme...` 改为 `:?Set JWT_SECRET_KEY in .env`（与 `POSTGRES_PASSWORD` 一致），让 compose 直接拒绝 up。

### P2-2：前端 npm 依赖中有 8 个 high + 12 个 moderate
- **重点 high 项**：
  - `lodash <=4.17.23` GHSA-r5fr-rjxr-66jc（template 注入 RCE）
  - `serialize-javascript <=7.0.2` GHSA-5c6j-r48x-rmvq（RegExp.flags RCE）
  - `flatted <=3.4.1` 原型污染
  - `vite <=6.4.1` path traversal（dev 服务器）
  - `dompurify <=3.3.3` ADD_TAGS bypass（**项目未用 ADD_TAGS，安全**）
  - `axios <1.15.0` NO_PROXY SSRF
- **修复**：批量 `npm audit fix`，对 lodash/serialize-javascript/flatted 做主版本升级试跑；vite 升 6.5+。
- **注意**：dompurify CVE 在本项目调用模式下不可触发（已用严格白名单+无 ADD_TAGS），可不紧急升。

### P2-3：响应头出现重复（X-Frame-Options、X-Content-Type-Options 等）
- **现象**：curl `-D -` 显示多个安全头出现两次，说明 nginx 与 FastAPI 都在 set。
- **影响**：浏览器对重复 XFO 的处理不同实现略有差异（SAMEORIGIN vs DENY）；审计噪音。
- **修复**：统一在 nginx 层设置，删除 FastAPI 中间件里的重复（或反之）。

### P2-4：CI 第三方 actions 未 SHA-pin
- **位置**：`.github/workflows/*.yml`（`actions/checkout@v4` `actions/setup-python@v5` 等）
- **缓解**：全是 `actions/*` 官方 action，被劫持概率低。
- **修复**：用 `pin-github-actions` / `dependabot` 自动 SHA pin（最佳实践，但在第三方 action 出现前不紧急）。

### P2-5：CSP 含 `'unsafe-eval'`
- **位置**：response header `script-src 'self' 'unsafe-eval' https://analytics.fojin.app`
- **修复**：定位需要 eval 的代码（可能是某图表/markdown 渲染依赖），切换到不需要 eval 的实现，或加 `wasm-unsafe-eval` 仅放开 wasm。低收益，可缓做。

### P2-6：上传文件仅校验扩展名，未校验 magic bytes
- **位置**：`backend/app/api/chat.py:128-137`
- **现状**：扩展名白名单 + 10MB 上限 + chunked read + uuid 重命名 + parse_attachment 各 parser 内部 try/except——已经相当稳。
- **修复**（可选）：用 `python-magic` 校验前 N 字节与扩展名匹配；防止 .pdf 实际是 docx 时让 LLM 拿到误导内容。

---

## P3 / 误报（已验证）

| 项 | 来源 | 结论 |
|---|---|---|
| `bandit B608` SQL injection @ rag_retrieval.py:102 | bandit | 误报。VALUES 由 `int(r["text_id"])` 等显式 int 转换后插值，无用户输入。 |
| 6× `semgrep avoid-sqlalchemy-text` @ knowledge_graph.py | semgrep | 误报。`pred_filter`/`where_clause`/`conditions` 全是硬编码字符串字面量，用户值均通过 `:named` 参数绑定。 |
| `semgrep use-defused-xml` @ tei_84000_parser.py:23 | semgrep | 误报。实际用 `defusedxml.ElementTree.fromstring`，bare `ET` 仅用作 `ET.ParseError` 异常类型。 |
| 4× `python-logger-credential-disclosure` @ auth.py / chat.py | semgrep | 误报。日志记录的是 `user_id` `ip` 字符串，无 secret 内容。 |
| `insecure-hash-algorithm-sha1` × 2 @ knowledge_graph.py | semgrep | 误报。SHA1 仅作 redis cache key 哈希，已 nosec 标注。 |
| `gitleaks generic-api-key` @ test_auth.py:234 | gitleaks | 误报。`sk-1234567890abcdef` 是测试 fixture。 |
| `npm audit dompurify` GHSA-39q2-94rc-95cp | npm | 不可触发。项目用严格 ALLOWED_TAGS 白名单且无 ADD_TAGS。 |
| `vite <=6.4.1` path traversal | npm | 仅影响 vite dev server，生产部署使用 nginx 静态托管，不可触发。 |

---

## 性能基线

| 指标 | 测量 | 评价 |
|------|------|------|
| `https://fojin.app/` TTFB | 157–237 ms（3 次） | 良好 |
| `/api/health` 端到端 | 200 ms | 良好（含 PG/ES/Redis 健康聚合） |
| `/api/search?q=慈悲&size=10` | 182–219 ms | 良好（ES 召回） |
| 主 JS bundle | 87 KB(br) / 227 KB(raw) | 合理（含 antd + react） |
| 整站 brotli/gzip | ✅ 启用（content-encoding: br） | 良好 |
| HSTS preload | `max-age=63072000; includeSubDomains; preload` | ✅ |
| 锁定文件大小 | 768 npm prod 包，69 python 包 | 偏大（deck.gl + maplibre + d3 三套图形栈），首屏需依赖 lazy chunking |

**性能层暂未发现明显回归**。建议下一步用 `/benchmark` skill 跑 LCP/CLS/INP（需 Chrome 实跑，超出当前 headless 范围）。

---

## codex 复核标记（待执行）

P0-1 与 P1-2 涉及加密策略与 trust boundary 决策，建议用 `/codex challenge` 让 GPT 独立挑战：
- P0-1 迁移路径：是否需要保留向后兼容 v1，还是强制全量重加密 + 通知用户重新填 key？
- P1-2 修复方案：取 last-XFF 还是用 uvicorn `--forwarded-allow-ips`？sg-vps + cloudflare(?) 链路下的 trusted proxy 列表如何配置？

---

## 已扫但未覆盖的层

| 层 | 状态 | 备注 |
|---|------|------|
| Trivy 镜像扫描 | ❌ 跳过 | trivy 未安装；建议本地或 CI 加 `trivy fs --severity HIGH,CRITICAL` |
| 容器运行时（VPS） | ❌ 计划之外 | 如需，参考 memory `project_fojin_disk_defense.md` + `feedback_vps_listener_scan.md` 手动跑 listener 扫描 |
| Lighthouse / LCP | ❌ 跳过 | 需 Chrome 实跑，本会话纯 headless |
| 渗透测试（active） | ❌ 跳过 | 仅静态审计；动态 fuzz / IDOR 探测建议另起（OWASP ZAP / nuclei）|

---

## 工具覆盖矩阵

| 工具 | 跑了什么 | 报告路径 |
|------|----------|----------|
| gitleaks 8.18 | work tree + 全 git history（487 commits） | `/tmp/gitleaks-history.json` |
| pip-audit 2.10 | `backend/requirements.txt` | `/tmp/pip-audit-prod.json` |
| npm audit | `frontend/` + `workers/prerender/` | `/tmp/npm-audit-frontend.json`, `/tmp/npm-audit-workers.json` |
| bandit | `backend/app/`（severity ≥ medium） | `/tmp/bandit.json` |
| semgrep 1.162 | `p/security-audit` + `p/owasp-top-ten` 全仓 | `/tmp/semgrep.json` |
| 人工审 | crypto.py / rate_limit.py / docker-compose.yml / nginx.conf / chat.py upload / sanitize.ts | — |
| curl 性能探测 | fojin.app 首页 + /api/health + /api/search | inline |

---

**报告结束**。修复清单已按 P0→P2 排序，每项含 file:line 证据 + CWE + 具体修复步骤；P0-1 与 P1-2 建议下一步用 `/codex` 复核迁移方案再下手。
