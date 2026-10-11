# 「这句经，佛真的说过吗？」核对页设计

日期：2026-10-11
状态：已定稿，待实施
分支：`feat/verify-page`

## 1. 目标

一个任何人都能用的页面：粘贴一句「佛说」，告诉他**它在不在大藏经里、出自哪部经、是不是佛经里的话**，并给出一张能在微信里长按保存转发的结果图。

这是「全球增长」子项目 ②（见用户记忆 `global-growth-initiative`）。用户拍板：**明确回答「是不是佛说」，按藏经分类**；首版形态由我评估后定为「独立页 + 可分享链接 + 服务端渲染的结果图」。

**不做**：白话解释（链到 /chat 让小津解释）、非汉文藏经、用户账号/历史记录、批量核对。

## 2. 关键事实（实测，2026-10-11，生产 `/api/verify/quote`）

| 集合 | n | 结果 |
|---|---|---|
| 名句 | 25 | 25 exact |
| 随机抽取原文（转简体、跨 CBETA 硬换行） | 20 | 20 exact |
| 网传假「佛说」 | 25 | 25 absent |
| 真经文 + 编造续句 | 5 | 5 absent（**整句判未见，closest 为空**） |

- **判真伪 75/75 正确，可直接用。**
- **找出处不能用**：名句的本经只有 7/25 出现在返回的 5 条里，排第一的 1/25。原因：`_es_candidates` 按 BM25 取前 5，注疏反复引用同一句、分数高过本经（「应无所住而生其心」前 5 全是 X 续藏注疏）。
- `text_contents` 索引有 `cbeta_id` keyword 字段 → 可用 painless 脚本排序，在召回阶段把本经排前。
- 已有服务端出图设施：`app/api/og.py`（Pillow + Noto CJK，1200×630，<200ms）。
- `/api/verify/quote` 限流 30/分钟/IP。

## 3. 方案

### 3.1 出处排序（`quote_lookup.py`）

开放世界的 phrase 召回改为**按藏经次序排序**而非 BM25：大正藏 T（按经号）→ 南传汉译 N → 卍续藏 X → 其他，取前 10 个候选、按此次序 PG 逐字确认，凑满 5 条即停。大正藏经号本身就是「阿含→般若→法华→华严→宝积→涅槃→大集→经集→密教→律→释经论→毗昙→中观→瑜伽→论集→经疏→律疏→论疏→诸宗→史传→事汇」的顺序，所以首条即「最早、最接近原典」的出处。`QuoteMatch` 新增 `canon_class` 字段（向后兼容，MCP 调用方同样受益）。

### 3.2 藏经分类（`app/services/canon_class.py`）

| class | 范围 | 页面结论 |
|---|---|---|
| `sutra` | T0001–T1420（经藏+密教）、N（南传汉译） | ✅ 佛经里的话 |
| `vinaya` | T1421–T1504 | 出自律典 |
| `treatise` | T1505–T1692 | 出自论（菩萨/论师所造），不是佛经原文 |
| `commentary` | T1693–T1850 | 出自注疏 |
| `school` | T1851–T2025 | 出自宗派著作 / 祖师著作（如《六祖坛经》） |
| `history` | T2026–T2184 | 出自史传、目录等 |
| `apocrypha` | T2865–T2920（疑似部） | 出自疑伪经 |
| `later` | X、J 及其他汉文续藏 | 出自后世注疏、语录 |
| `unknown` | 其余 | 只报出处 |

措辞纪律：`sutra` 写「出自佛经《X》」，**不写「佛亲口所说」**（经中也有菩萨、弟子所说）。

### 3.3 逐句核对（`app/services/claim_check.py`，`GET /api/verify/claim?q=`）

1. 整句先核对；整句逐字命中 → 一段结果。
2. 否则按中文标点切小句，不足 4 字的并入相邻句，最多 8 句，逐句 `verify_quote`。
3. 总结论 `verdict`：`sutra`（全部命中且首条出处为 sutra）/ `not_sutra`（全部命中但首条出处非 sutra，附 class）/ `partial`（部分命中）/ `absent`（均未命中）。
4. 输入上限 200 字；独立限流 `rate_limit_verify_claim = 10`/分钟/IP（一次最多 9 次查找）。

### 3.4 结果图（`GET /api/og/verify?q=`）

复用 `og.py` 的字体与画布：结论徽章（颜色区分）+ 原句（逐句着色：命中/未见）+ 首位出处（经名·卷）+「佛津 FoJin · fojin.app/verify」。`Cache-Control: public, max-age=86400`。页面上以 `<img>` 呈现 → 微信里长按即可保存/转发。（Helmet 也写了 og:image，但 `/verify?q=` 由 nginx 返回静态 shell，不执行 JS 的抓取器拿不到它——链接预览图仍是通用图；要做需后端为 `?q=` 注入，本期不做。）

### 3.5 页面（`/verify`，`VerifyPage.tsx`）

输入框 + 示例（真/假/拼接各一）→ 提交写入 `/verify?q=…`（可分享）→ 结论卡片 + 逐句出处（链到阅读器）+ 结果图 +「问小津这句话的意思」（→ `/chat?q=`）。三语 i18n。导航栏加入口。

SEO：`/verify` 静态 shell（三语，复用子项目 ① 的 buildShells / nginx / sitemap 机制）；`/verify?q=` 页 Helmet 输出 `noindex, follow`，canonical 指 `/verify`。

## 4. 验收

- **留出集**（`backend/eval/verify_claim/heldout.json`，20 句，调参前已提交）：首位出处 ∈ accept **≥ 80%**，class 正确 ≥ 80%。
- 发现集（`discovery.json`）：假「佛说」10/10 `absent`；拼接 5/5 `partial` 且真的那半句命中。
- 单测：分类边界、切句、verdict 组合、排序脚本参数、限流键、出图（含 CJK）。
- 真浏览器：桌面 + 390px 手机，结果图可见、长按保存（WeChat 无法自动化，至少验证 `<img>` 为真实 PNG）。
- 上线后：生产按留出集跑一次，成绩写进 PR。
