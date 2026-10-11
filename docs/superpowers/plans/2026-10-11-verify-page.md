# 核对页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/verify`——粘贴一句「佛说」，给出是否在大藏经、出自哪部、是不是佛经，并出一张可长按保存的结果图。

**Architecture:** 后端三层：`canon_class`（经号→藏经分类与排序键）→ `quote_lookup` 召回按藏经次序排序 → `claim_check`（整句/逐句 + 总结论，进程内 TTL 缓存）→ `/api/verify/claim` 与 `/api/og/verify`。前端 `VerifyPage` + 三语 shell。

**Tech Stack:** FastAPI、Elasticsearch painless 脚本排序、Pillow（复用 `app/api/og.py`）、React + antd、子项目 ① 的 buildShells/nginx/sitemap 机制。

Spec：`docs/superpowers/specs/2026-10-11-verify-page-design.md`

## Global Constraints

- 结果图**只接受 `q`**，结论一律服务端重新计算（防伪造带佛津品牌的图）。
- `sutra` 结论措辞是「出自佛经」，不写「佛亲口所说」。
- 输入 ≤ 200 字；逐句最多 8 句；`/api/verify/claim` 与 `/api/og/verify` 各自 10/分钟/IP。
- 新增断言先跑红；提交不加任何 Claude 署名；后端 `ruff==0.9.7`；前端 lint 0 warning、i18n ratchet、tsc。
- 留出集 `backend/eval/verify_claim/heldout.json` 只在最后验收时看。

### Task 1: `canon_class.py`
- Create `backend/app/services/canon_class.py`：`CanonClass` Literal；`canon_class(cbeta_id: str | None) -> CanonClass`（按 spec §3.2 区间）；`CANON_ORDER_SCRIPT: str`（painless：T→0+号，N→50000+号，X→100000+号，其他→200000+号，缺失→9e9）。
- Test `backend/tests/test_canon_class.py`：各区间两端（T0001/T1420 sutra、T1421 vinaya、T1666 treatise、T1803 commentary、T2008 school、T2076 history、T2919 apocrypha、X0508 later、N0006 sutra、J/None unknown/later），带字母后缀的号（T0236a、T1510b）。
- Commit `feat(verify): 藏经分类与排序键`

### Task 2: 召回按藏经次序排序
- Modify `quote_lookup.py`：`_es_candidates(..., canonical_order: bool = False)` 为 True 时 body 加 `"sort": [{"_script": {"type": "number", "script": {"source": CANON_ORDER_SCRIPT}, "order": "asc"}}]`；开放世界 phrase 召回改用 `canonical_order=True, size=10`；`_match_from` 填 `canon_class`。`QuoteMatch` 加 `canon_class: str | None = None`。
- Test：fake ES 断言请求体带脚本排序、size=10；候选按给定顺序确认，凑满 5 停；`canon_class` 填充。更新 `test_quote_lookup*.py` 里依赖旧 size 的断言。
- Commit `feat(verify): 开放世界召回按藏经次序排序，首条即最早出处`

### Task 3: `claim_check.py` + `/api/verify/claim`
- Create `app/services/claim_check.py`：`split_clauses(text) -> list[str]`；`async check_claim(db, es, text) -> ClaimVerdict`（spec §3.3；TTL 缓存 3600s、上限 512 条，键为 `normalise_for_match(text)`）。
- Create schemas `ClaimSegment{text, found, source: QuoteMatch|None, similarity}`、`ClaimVerdict{query, verdict, source_class, segments}`。
- Endpoint `GET /api/verify/claim?q=`（≤200 字，过短 422）；`STRICT_PATHS` 加 `/api/verify/claim` 与 `/api/og/verify`，配置 `rate_limit_verify_claim: int = 10`。
- Test：切句（标点、短句并入、上限 8）；verdict 四种组合（monkeypatch `verify_quote`）；缓存命中不再调用；endpoint 422/200；限流表含两条路径。
- Commit `feat(verify): 逐句核对与总结论接口`

### Task 4: 结果图 `/api/og/verify`
- Modify `app/api/og.py`：`GET /og/verify?q=` → `check_claim` → Pillow 画卡（结论徽章色：sutra 绿、not_sutra 琥珀、partial 橙、absent 灰；逐句着色；首位出处；页脚品牌 + `fojin.app/verify`）；`Cache-Control: public, max-age=86400`。
- Test：返回 `image/png`、尺寸 1200×630；四种 verdict 都能出图；超长输入截断不报错；**URL 里塞 verdict 参数被忽略**。
- Commit `feat(verify): 服务端渲染结果图`

### Task 5: 前端页面
- Create `frontend/src/pages/VerifyPage.tsx`（+ `.test.tsx`）、`frontend/src/api/client.ts` 加 `verifyClaim(q)`；`App.tsx` 路由；`Layout.tsx` 导航项 `nav.verify`；三语 locale 键。
- 行为：提交写 `?q=`；读取 `?q=` 自动核对；结论文案按 verdict×class；逐句列表链阅读器；`<img src="/api/og/verify?q=…">` + 「长按图片保存」；「问小津」→ `/chat?q=`；`?q=` 时 Helmet `noindex, follow`，canonical/hreflang 走 `<LangAlternates path="/verify">`。
- Test：四种 verdict 的渲染文案（mock API）；`?q=` 自动请求；noindex 仅在有 q 时出现。
- Commit `feat(verify): 核对页`

### Task 6: SEO 接入与整支验收
- `staticPages.json` 加 `verify`（zh + en）；`nginx.conf` 加 `location = /verify`（含 html-no-cache）与大小写 301；sitemap `STATIC_PAGES` 加 `/verify`；`nginx-lang-check.sh` 加 `/verify` 三语检查；修 `deploy/seo_lang_prod_check.sh` 的 pipefail+`grep -q` 误报，并加 `/verify`。
- 本地对生产 ES 跑不了 → 验收脚本 `backend/eval/verify_claim/run_against.py <base-url>`：对某个部署（本地或生产）跑发现集与留出集，输出首位命中率、class 正确率、假/拼接判定。上线前用当前生产只能测「旧排序」作对照；上线后测新排序。
- 门禁全跑 + 真浏览器（桌面 + 390 宽）。
- 整支审查（新上下文子代理）→ 修 → PR，不合并。
