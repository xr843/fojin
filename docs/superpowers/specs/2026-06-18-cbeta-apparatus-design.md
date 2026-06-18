# CBETA 校勘异文 (Critical Apparatus) — 设计

**日期**: 2026-06-18
**状态**: 已批准,实施中
**roadmap**: CBETA 借鉴 5 项中的 #1(ROI 最高)。后续 #2 行锚点 / #3 NER→KG / #4 concordance / #5 多版本并排 reader。

## 背景与动机

FoJin 已基本全量吸收 CBETA 全文(prod 实测 2.84 亿字、大正+卍续按字数 ~100%、gaiji 全表 31,653)。但 `backend/app/core/xml_parser.py` 只抽底本平文,`SKIP_TAGS` 丢弃 `<app>`/`<rdg>`/`<note>` —— **CBETA 20 年最核心的学术贡献「校勘异文」(宋/元/明/麗等校本的异读)被完全丢弃**。

源 XML 里这层数据齐备,纯属"捡回被丢掉的层"。它直接服务于用户的校勘/标点研究项目,且为 FRBR witness 脊椎从「经级」下沉到「字级」。

## 数据结构(已对真实 XML 验证 — T01n0001)

CBETA 用 **standoff(分离式)apparatus**:

- 正文(`<body>`):`...<anchor xml:id="beg0001004" n="0001004"/>辨<anchor xml:id="end0001004"/>之以法相...`,夹带 `<lb n="0001a09"/>` 页·栏·行标记。
- 校勘(`<back><cb:div type="apparatus">`):
  `<app from="#beg0001004" to="#end0001004"><lem wit="#wit.orig">辨</lem><rdg resp="#resp2" wit="#wit1">辯</rdg></app>`
- 头部声明:`<witness xml:id="wit1">【宋】</witness>`、`<respStmt xml:id="resp2"><name>Taisho</name></respStmt>`。
- 语义:大正底本作「辨」,宋本(wit1)作「辯」,由 Taisho 校订。
- 规模:单 T0001(22 卷)= 3,215 条 app / 6,882 anchor。全藏量级为百万行,但仅是行存储。
- `<rdg>` 特例:`<space quantity="0"/>` = 校本无此字(omission);`<rdg>` 内可含 `<g>` gaiji;`wit="#wit1 #wit2"` = 多校本。

**重要**:每经 header 独立声明 witness/resp 的 xml:id,不同经的 `wit1` 含义不同 → 解析时必须**就地译成可读 siglum**(【宋】)入库,绝不存 raw id。

## 存储(决策:独立两表)

`text_apparatus`:
- `id, text_id (FK buddhist_texts), juan_num`
- `char_start, char_end` — 在该 juan 最终 `content` 字符串中的字符偏移
- `lemma` — 底本读法文本(如「辨」)
- `lemma_siglum` — 底本 siglum(如【大】/【CB】)
- `app_n` — CBETA app 编号(如 `0001004`),便于回链与去重
- `created_at`

`apparatus_reading`(一条 app 对应多个校本读法):
- `id, apparatus_id (FK, CASCADE)`
- `reading` — 校本读法文本(如「辯」);omission 时为空串
- `witnesses` — siglum 列表(text[]/JSON,如 `["【宋】","【元】"]`)
- `resp` — 改订者(CBETA / Taisho / …)
- `is_omission` — bool,`<space>` 时 true

附带(决策:顺手存,本期不做 UI):`text_line_anchor` 轻表存 `<lb>` 行锚 —— `text_id, juan_num, char_offset, line_ref(如 "0001a09")`。为 roadmap #2(URN 行级定位 + RAG 引文可核验)铺路。

> 替代方案 text_contents 挂 JSONB 已否决:独立表利于全局校勘统计/查询与未来 concordance(#4),契合"校勘研究工具"目标。

## 解析改造

**关键不变式**:`content[char_start:char_end] == lemma`(用单测钉死)。偏移必须按"已 strip note/app、已 resolve gaiji、已插段落空行"后的**最终 content** 计 —— 因此 anchor / lb 偏移的记录必须与正文构建在**同一遍**完成,不能用原始 XML 偏移。

1. `parse_tei_xml` 增强:遍历 body 时,遇 `<anchor xml:id="beg.../end...">` 记录其在当前 juan content 中的字符偏移(`anchor_id → offset`);遇 `<lb>` 记录行锚偏移。返回结构新增 `anchors`、`line_anchors`。
2. 新增 `parse_witnesses(root) -> {xml_id: siglum}`、`parse_resp(root) -> {xml_id: name}`。
3. 新增 `parse_apparatus(root, witnesses, resp) -> [{app_n, from, to, lemma, lemma_siglum, readings:[{reading, witnesses, resp, is_omission}]}]`。
4. import_content 接线:用 anchor offset map 把每条 app 的 `from/to` 解析成 `(juan_num, char_start, char_end)`,写 apparatus 两表 + line anchor 表。

边界处理(全部不静默,log 计数):
- anchor 跨 juan / 找不到 offset → 跳过 + 计数。
- rdg 内 `<g>` gaiji → 复用 `_resolve_gaiji`。
- `<space>` → is_omission=true。
- `content[char_start:char_end] != lemma`(对齐失败)→ 跳过 + 计数(可能 anchor 跨标签)。

## API

新增懒加载端点(避免正文 payload 被数千条撑爆):
`GET /texts/{text_id}/juans/{juan_num}/apparatus`
→ `{ entries: [{char_start, char_end, lemma, lemma_siglum, readings:[{reading, witnesses, resp, is_omission}]}] }`

## 展示(前端 `TextReaderPage`)

- 渲染正文时,按 `char_start/char_end` 给有异文的字加虚线下标(不破坏 reflowText)。
- hover/点击 → popover:「【大】辨 / 【宋】辯(CBETA 改)」,列出各校本。
- 「显示校勘」开关(默认关,避免干扰普通读者)。

## 测试(TDD,先红后绿)

- parser 单测:最小 TEI(body anchors + back apparatus + header witness),断言条目 offset/lemma/readings/witness 正确。
- 对齐不变式:`content[char_start:char_end] == lemma`。
- 用例:omission(`<space>`)、rdg 内 gaiji、多 witness、跨 juan 边界跳过、行锚偏移。
- API 测:apparatus 端点结构。

## 增量实施顺序(每步可独立验证)

1. migration + models + schema(空表)。
2. parser:apparatus + anchor/lb offset 解析 + 单测。
3. import 接线 + **先试跑 T0001 验证对齐不变式**(prod 只读取样核对)。
4. API 端点 + 测。
5. 前端 reader 标记 + popover。
6. 全量 backfill(checkpoint 分批,参照 import_content)。

worktree 隔离;走 ruff → pytest → reviewer agent → PR → merge → 部署验证。
