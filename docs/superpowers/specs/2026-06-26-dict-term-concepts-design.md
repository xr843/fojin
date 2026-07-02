# 辞典多语种术语概念层 — Phase 1 (结构化骨架)

**日期:** 2026-06-26
**状态:** 设计已批准,实施中
**分支:** `feat/dict-term-concepts`

## 目标

把 39 部辞典(中梵巴藏英蒙满,747,622 条)从"各语种孤立"升级为可跨语检索的**概念层**:
搜「涅槃」→ 上方出现一张多语种概念卡(汉 涅槃 · 梵 nirvāṇa · 巴 nibbāna · 藏 mya ngan las 'das pa · …),
卡下接现有的跨辞典分组结果。**纯增量,不改现有 `/search` 与浏览逻辑。**

这一层不只服务辞典 UI——结构化的「中↔梵↔巴↔藏」术语等价表,是 dict + chat(让回答引真实对应而非 LLM 自由发挥)+ 跨藏对齐主线**共用的多语术语基建**。

Phase 1 只建**高精度结构化骨架**,把噪声大的"释义罗马化抽取"留到 Phase 2。

## 已验证的真实数据形态(建表器据此)

- **翻譯名義大集 (`dila-mvp`, source_id 661, 9379 条)**:梵文 headword;`definition` 一条内并列
  IAST / 天城体 / 汉(可多个) / 藏文 Wylie / 藏文 Unicode,以换行+缩进分隔。`entry_data` 为 null。
  例:`nirvāṇam` → 汉「涅槃」「清淨涅槃」+ 藏「mya ngan las 'das pa」。
- **四譯合璧輯要 (`siyi-hebi`, source_id 678, 1057 条)**:`definition` 用标签并列
  `【梵】…【滿】…【蒙】…【漢】…`;`entry_data.definition_html` 同结构带 `<br>`。
- **罗马 headword 支点**:MW / Edgerton(梵)、DPD / PTS / NCPED(巴)按各自罗马 headword 入库,
  归一化后可与概念 key 串联。
- **辞典词条模型** `dictionary_entries`:`id, headword, reading, definition, source_id, lang, entry_data(JSON), external_id`。

## 数据模型(2 张新表,migration 0160,down_revision 0159)

### `term_concepts`
| 列 | 类型 | 说明 |
|----|------|------|
| `id` | PK int | |
| `key` | String(200), unique, index | 归一化 IAST(小写+去变音符+去尾 m/ḥ),如 `nirvana` |
| `sanskrit` | String(200) null | 展示用 IAST,如 `nirvāṇa` |
| `devanagari` | String(200) null | |
| `pali` | String(200) null | |
| `tibetan` | String(300) null | Wylie 或藏文 |
| `chinese` | String(200) null | 代表中文词形 |
| `english` | Text null | |
| `created_at` | timestamptz | |

代表词形冗余存在概念上 → 概念卡零 join 直接渲染。

### `term_concept_entries`(概念 ↔ 词条 多对多)
| 列 | 类型 | 说明 |
|----|------|------|
| `id` | PK int | |
| `concept_id` | FK → term_concepts.id, index | |
| `dict_entry_id` | FK → dictionary_entries.id, index | |
| `lang` | String(10) | |
| `method` | String(40) | 建链规则:`mvp` / `siyi_tag` / `romanized_join` |
| `confidence` | String(10) | `high` / `medium` |

`UniqueConstraint(concept_id, dict_entry_id)`。`method`/`confidence` 让 Phase 2 可审计可回滚。

## 建表管线 — `backend/scripts/build_term_concepts.py`(离线,幂等 upsert,不进请求路径)

纯函数(CI 单测守):
- `normalize_iast(s) -> key`:NFKD 去变音符 → 小写 → 去尾 `m`/`ḥ`/空白。
- `classify_script(segment) -> {iast|devanagari|han|tibetan|other}`:按 Unicode 块判定。
- `parse_mvp_definition(def) -> {sanskrit, devanagari, chinese[], tibetan}`:按行切分 + classify_script 归桶(**不依赖位置**,容忍 MVP 的不规则嵌套)。
- `parse_siyi_definition(def) -> {梵, 漢, 滿, 蒙}`:按 `【x】` 标签切分。

流程(精度高→低):
1. MVP → 建概念骨架(key=normalize(sanskrit)),填 sanskrit/devanagari/chinese/tibetan;链该词条(method=`mvp`)。
2. 四譯合璧 → 按梵文 key upsert 概念,补 chinese;链词条(method=`siyi_tag`)。
3. 罗马 headword 串联:MW/Edgerton/DPD/PTS/NCPED 的 headword 归一化,命中已有 key → 链词条 + 补 pali/sanskrit 展示(method=`romanized_join`)。
4. 中文回链:按 concept.chinese 精确匹配 佛光/丁福保 等中文 headword 词条 → 链入(method=`romanized_join`, confidence=medium)。

对 10 万+词条是批处理,像 eval baseline 一样在 prod 容器内跑一次:
`docker compose exec -T backend python -m scripts.build_term_concepts`。**只写新表,不碰现有词条。**

## ⚠️ Pali 范围边界(Phase 1)

梵↔汉↔藏靠 MVP/四譯合璧,是真·古典对照,精度高。梵巴词形常不同(nirvāṇa vs nibbāna),
ASCII 折叠不会自动相等 → **Phase 1 Pali 链接 best-effort**:词形巧合相同(bodhi=bodhi)能链,
其余留 Phase 2 的梵巴规则层。不制造"全 Pali 覆盖"假象。

## API

`GET /api/dictionary/concept?q=<词>`(新端点,不改 `/search`):
把中/梵/巴/藏任一词形解析到概念(先精确匹配 chinese/sanskrit/pali/tibetan,再归一化 key 匹配),
返回:
```json
{ "concept": {"sanskrit","pali","tibetan","chinese","english","devanagari"},
  "entries_by_lang": [ {"lang":"sa","entries":[{id,headword,source_name,definition_preview}]}, ... ] }
```
未命中 → `{"concept": null, "entries_by_lang": []}`(200,优雅降级)。

## 前端

- `frontend/src/components/ConceptCard.tsx`:命中概念时渲染于结果上方。
  多语种词形横排,每个可点(填入搜索/跳该语种)。无命中不渲染。
- `DictionaryPage.tsx`:在搜索态并行发 `/concept` query;有 concept 才显示卡。
- `client.ts` 加 `getDictConcept`;i18n 加 `dict.concept.*`(zh/zh-Hant/en)。

## 测试

- 单测(CI,纯逻辑):`normalize_iast` / `classify_script` / `parse_mvp_definition` / `parse_siyi_definition`。
- 建表器:fixture 跑一遍,断言 `涅槃 ↔ nirvāṇa ↔ 藏` 正确成链。
- API:`/concept` 已知词返回结构正确、未知词 200 空返回。

## 上线

migration 加空表(零风险)→ prod 容器跑建表脚本 → 前端发版。
部署前核 prod `alembic_version`(应为 0159)与文件链一致(见 feedback_fojin_alembic_chain_check)。
