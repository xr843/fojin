# AI Chat Evaluation System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible evaluation system for the AI Q&A feature: a curated test set, an automated scoring script, and a baseline report — so every future optimization can be measured.

**Architecture:** A JSON test set with 90 questions across 6 categories, each with reference answers and scoring rubrics. An async Python evaluation script calls the real RAG pipeline + LLM on the production database, scores each answer on 4 dimensions (retrieval relevance, citation accuracy, answer completeness, hallucination), and outputs a Markdown report with per-category and overall scores.

**Tech Stack:** Python 3.12, pytest, asyncio, httpx, SQLAlchemy async (existing stack). Evaluation runs against the real DB (production or local) — no mocks.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/eval/test_set.json` | 90 curated Buddhist Q&A evaluation questions |
| `backend/eval/run_eval.py` | Main evaluation script: runs questions through RAG+LLM, scores, outputs report |
| `backend/eval/scorer.py` | Scoring logic: LLM-as-judge + rule-based checks |
| `backend/eval/README.md` | Usage instructions and scoring rubric documentation |
| `backend/eval/__init__.py` | Package marker |

---

### Task 1: Create the Evaluation Test Set

**Files:**
- Create: `backend/eval/__init__.py`
- Create: `backend/eval/test_set.json`

- [ ] **Step 1: Create eval package**

```python
# backend/eval/__init__.py
# AI Chat evaluation system
```

- [ ] **Step 2: Create test set JSON with 90 questions across 6 categories**

The test set has 90 questions (15 per category) with this schema:

```json
{
  "version": "1.0",
  "description": "FoJin AI Chat evaluation test set",
  "created": "2026-04-01",
  "questions": [
    {
      "id": "term-001",
      "category": "term_explanation",
      "question": "五蕴是什么？",
      "reference_answer_points": [
        "五蕴指色、受、想、行、识",
        "色蕴指物质/形体",
        "受蕴指感受",
        "想蕴指概念/表象",
        "行蕴指意志/心所",
        "识蕴指意识/了别"
      ],
      "reference_sources": ["般若波罗蜜多心经", "杂阿含经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    }
  ]
}
```

Categories (15 questions each):
1. **term_explanation** (名相解释): 五蕴、十二因缘、四圣谛、八正道、三法印、六度、涅槃、菩提心、缘起、空性、中道、三学、四摄、般若、佛性
2. **source_lookup** (经文出处): 色即是空出处、应无所住而生其心出处、一切有为法如梦幻泡影出处、etc.
3. **historical** (人物历史): 鸠摩罗什翻译、玄奘西行、禅宗六祖、龙树中观、天台宗创立、etc.
4. **comparative** (义理比较): 唯识与中观区别、大小乘区别、禅净差异、南传北传比较、etc.
5. **practice** (修行实践): 初学禅修方法、念佛法门、持戒要点、观呼吸方法、etc.
6. **out_of_scope** (无法回答/非佛学): 天气、股票、编程、物理、政治 — 期望礼貌拒绝或引导回佛学

Full 90 questions with reference answers will be included in the JSON file. Below is the complete content:

```json
{
  "version": "1.0",
  "description": "FoJin AI Chat evaluation test set — 90 questions across 6 categories",
  "created": "2026-04-01",
  "categories": {
    "term_explanation": "名相解释 — 佛学术语和概念的准确解释",
    "source_lookup": "经文出处 — 引用查证和经典定位",
    "historical": "人物历史 — 佛教历史人物和事件",
    "comparative": "义理比较 — 不同宗派/概念的对比分析",
    "practice": "修行实践 — 具体修行方法和建议",
    "out_of_scope": "超出范围 — 非佛学问题，应礼貌拒绝"
  },
  "scoring_rubric": {
    "retrieval_relevance": "检索相关性 (0-3): 0=完全无关, 1=部分相关, 2=大部分相关, 3=高度相关",
    "citation_accuracy": "引用准确性 (0-3): 0=无引用或全错, 1=有引用但不准确, 2=引用基本正确, 3=引用准确且格式规范",
    "answer_completeness": "回答完整性 (0-3): 0=未回答, 1=部分回答, 2=基本完整, 3=全面深入",
    "no_hallucination": "无编造 (0-1): 0=有明显编造, 1=无编造"
  },
  "questions": [
    {
      "id": "term-001",
      "category": "term_explanation",
      "question": "五蕴是什么？",
      "reference_answer_points": ["五蕴指色、受、想、行、识", "色蕴指物质形体", "受蕴指感受苦乐", "想蕴指概念表象", "行蕴指意志造作", "识蕴指了别认知"],
      "reference_sources": ["般若波罗蜜多心经", "杂阿含经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "term-002",
      "category": "term_explanation",
      "question": "十二因缘的内容和顺序是什么？",
      "reference_answer_points": ["无明、行、识、名色、六入、触、受、爱、取、有、生、老死", "十二因缘说明生死轮回的因果链", "由无明起至老死"],
      "reference_sources": ["缘起经", "杂阿含经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "term-003",
      "category": "term_explanation",
      "question": "四圣谛的核心教义是什么？",
      "reference_answer_points": ["苦谛：生命本质是苦", "集谛：苦的原因是贪嗔痴", "灭谛：苦可以止息即涅槃", "道谛：灭苦的方法是八正道"],
      "reference_sources": ["杂阿含经", "中阿含经", "转法轮经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "term-004",
      "category": "term_explanation",
      "question": "八正道分别是什么？",
      "reference_answer_points": ["正见、正思维、正语、正业、正命、正精进、正念、正定", "属于道谛的具体内容", "可分为戒定慧三学"],
      "reference_sources": ["杂阿含经", "中阿含经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "term-005",
      "category": "term_explanation",
      "question": "三法印是什么？与一实相印有什么关系？",
      "reference_answer_points": ["诸行无常、诸法无我、涅槃寂静", "三法印是判断是否为佛法的标准", "大乘以一实相印（诸法实相）统摄三法印"],
      "reference_sources": ["杂阿含经", "法华经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "term-006",
      "category": "term_explanation",
      "question": "六度波罗蜜分别是什么？",
      "reference_answer_points": ["布施、持戒、忍辱、精进、禅定、般若", "波罗蜜意为到彼岸", "是菩萨修行的六种方法"],
      "reference_sources": ["大般若经", "大智度论"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "term-007",
      "category": "term_explanation",
      "question": "涅槃的含义是什么？有哪些分类？",
      "reference_answer_points": ["涅槃意为寂灭、灭度", "有余涅槃：烦恼已断但肉身尚在", "无余涅槃：身心俱灭", "大乘还有自性清净涅槃、无住处涅槃等"],
      "reference_sources": ["涅槃经", "成唯识论"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "term-008",
      "category": "term_explanation",
      "question": "什么是菩提心？",
      "reference_answer_points": ["菩提心是上求佛道下化众生的心", "分愿菩提心和行菩提心", "是大乘佛教修行的根本动力"],
      "reference_sources": ["华严经", "大智度论", "菩提道次第广论"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "term-009",
      "category": "term_explanation",
      "question": "缘起法的核心含义是什么？",
      "reference_answer_points": ["此有故彼有，此生故彼生", "此无故彼无，此灭故彼灭", "一切法因缘和合而生，无自性"],
      "reference_sources": ["杂阿含经", "中论"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "term-010",
      "category": "term_explanation",
      "question": "般若波罗蜜多心经中「空」的含义是什么？",
      "reference_answer_points": ["空不是虚无，是指无自性", "色不异空空不异色", "五蕴皆空", "空是缘起性空，不是断灭空"],
      "reference_sources": ["般若波罗蜜多心经", "大般若经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "term-011",
      "category": "term_explanation",
      "question": "什么是中道？",
      "reference_answer_points": ["远离苦行和纵欲两种极端", "龙树中观的中道：不落有无二边", "八正道即是中道的实践"],
      "reference_sources": ["杂阿含经", "中论"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "term-012",
      "category": "term_explanation",
      "question": "戒定慧三学是什么？",
      "reference_answer_points": ["戒学：持戒律防非止恶", "定学：修禅定令心专注", "慧学：修智慧断烦恼", "三学是佛教修行的基本框架"],
      "reference_sources": ["杂阿含经", "大智度论"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "term-013",
      "category": "term_explanation",
      "question": "四摄法是什么？",
      "reference_answer_points": ["布施摄、爱语摄、利行摄、同事摄", "是菩萨摄化众生的四种方便"],
      "reference_sources": ["华严经", "大智度论"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "term-014",
      "category": "term_explanation",
      "question": "什么是如来藏思想？",
      "reference_answer_points": ["众生本具如来智慧德相", "如来藏即佛性、真如", "被烦恼覆盖但本性清净"],
      "reference_sources": ["如来藏经", "大般涅槃经", "楞伽经"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "term-015",
      "category": "term_explanation",
      "question": "阿赖耶识在唯识学中的含义是什么？",
      "reference_answer_points": ["第八识，藏识，含藏一切种子", "是轮回的主体", "具能藏、所藏、执藏三义", "是前七识的根本依"],
      "reference_sources": ["解深密经", "成唯识论", "瑜伽师地论"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "source-001",
      "category": "source_lookup",
      "question": "「色不异空，空不异色」出自哪部经？",
      "reference_answer_points": ["出自《般若波罗蜜多心经》", "属于般若部经典"],
      "reference_sources": ["般若波罗蜜多心经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "source-002",
      "category": "source_lookup",
      "question": "「应无所住而生其心」出自哪部经？",
      "reference_answer_points": ["出自《金刚般若波罗蜜经》", "六祖慧能因此句开悟"],
      "reference_sources": ["金刚般若波罗蜜经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "source-003",
      "category": "source_lookup",
      "question": "「一切有为法，如梦幻泡影」出自哪里？完整的偈颂是什么？",
      "reference_answer_points": ["出自《金刚般若波罗蜜经》", "完整偈颂：一切有为法，如梦幻泡影，如露亦如电，应作如是观"],
      "reference_sources": ["金刚般若波罗蜜经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "source-004",
      "category": "source_lookup",
      "question": "「照见五蕴皆空，度一切苦厄」出自哪部经的哪个段落？",
      "reference_answer_points": ["出自《般若波罗蜜多心经》", "位于经文开篇部分", "观自在菩萨行深般若波罗蜜多时"],
      "reference_sources": ["般若波罗蜜多心经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "source-005",
      "category": "source_lookup",
      "question": "「若以色见我，以音声求我，是人行邪道，不能见如来」出处是什么？",
      "reference_answer_points": ["出自《金刚般若波罗蜜经》", "说明不应以相见如来"],
      "reference_sources": ["金刚般若波罗蜜经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "source-006",
      "category": "source_lookup",
      "question": "「诸法因缘生，诸法因缘灭」这句话的出处是什么？",
      "reference_answer_points": ["出自《杂阿含经》或相关阿含部经典", "是缘起法的经典表述"],
      "reference_sources": ["杂阿含经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "source-007",
      "category": "source_lookup",
      "question": "「不生不灭，不垢不净，不增不减」出自哪部经？",
      "reference_answer_points": ["出自《般若波罗蜜多心经》", "描述空性的特征"],
      "reference_sources": ["般若波罗蜜多心经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "source-008",
      "category": "source_lookup",
      "question": "《法华经》的核心思想是什么？",
      "reference_answer_points": ["会三归一：声闻缘觉菩萨三乘归于一佛乘", "开权显实", "一切众生皆能成佛"],
      "reference_sources": ["妙法莲华经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "source-009",
      "category": "source_lookup",
      "question": "净土三经是哪三部经？",
      "reference_answer_points": ["《佛说阿弥陀经》", "《佛说无量寿经》", "《观无量寿佛经》"],
      "reference_sources": ["佛说阿弥陀经", "佛说无量寿经", "观无量寿佛经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "source-010",
      "category": "source_lookup",
      "question": "「三界唯心，万法唯识」的经典依据是什么？",
      "reference_answer_points": ["三界唯心出自《华严经》", "万法唯识出自唯识学传统", "《解深密经》《成唯识论》为重要依据"],
      "reference_sources": ["华严经", "解深密经"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "source-011",
      "category": "source_lookup",
      "question": "《楞严经》中的「楞严咒」在经文的什么位置？",
      "reference_answer_points": ["楞严咒位于《楞严经》第七卷", "是佛教最长的咒语之一"],
      "reference_sources": ["大佛顶首楞严经"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "source-012",
      "category": "source_lookup",
      "question": "「是诸法空相」后面的经文内容是什么？",
      "reference_answer_points": ["不生不灭，不垢不净，不增不减", "出自《心经》"],
      "reference_sources": ["般若波罗蜜多心经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "source-013",
      "category": "source_lookup",
      "question": "《维摩诘经》中维摩诘居士「一默如雷」的故事是怎样的？",
      "reference_answer_points": ["在入不二法门品中", "众菩萨各说不二法门", "文殊师利说无言无说", "维摩诘默然不语表示不二"],
      "reference_sources": ["维摩诘所说经"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "source-014",
      "category": "source_lookup",
      "question": "《地藏菩萨本愿经》中「地狱不空，誓不成佛」的原文是什么？",
      "reference_answer_points": ["地狱未空誓不成佛，众生度尽方证菩提", "体现地藏菩萨的大愿"],
      "reference_sources": ["地藏菩萨本愿经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "source-015",
      "category": "source_lookup",
      "question": "《坛经》中六祖慧能的「菩提本无树」偈颂完整内容是什么？",
      "reference_answer_points": ["菩提本无树，明镜亦非台", "本来无一物，何处惹尘埃", "与神秀的偈颂对照"],
      "reference_sources": ["六祖大师法宝坛经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-001",
      "category": "historical",
      "question": "鸠摩罗什翻译了哪些重要经典？",
      "reference_answer_points": ["《妙法莲华经》", "《金刚般若波罗蜜经》", "《维摩诘所说经》", "《阿弥陀经》", "《中论》《大智度论》等", "翻译风格意译为主"],
      "reference_sources": ["高僧传"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-002",
      "category": "historical",
      "question": "玄奘西行取经的历史背景和贡献是什么？",
      "reference_answer_points": ["唐代贞观年间西行印度", "在那烂陀寺学习", "带回大量梵文经典", "翻译了《大般若经》《瑜伽师地论》《成唯识论》等", "创立法相唯识宗"],
      "reference_sources": ["大唐西域记", "大慈恩寺三藏法师传"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-003",
      "category": "historical",
      "question": "禅宗六祖慧能的生平和主要思想是什么？",
      "reference_answer_points": ["唐代人，得五祖弘忍传法", "提倡顿悟成佛", "强调自性清净", "《坛经》是其核心著作", "从此禅宗分南北二宗"],
      "reference_sources": ["六祖大师法宝坛经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-004",
      "category": "historical",
      "question": "龙树菩萨对佛教的贡献是什么？",
      "reference_answer_points": ["创立中观学派", "著《中论》《大智度论》《十二门论》等", "提出八不中道", "被尊为八宗共祖"],
      "reference_sources": ["中论", "大智度论"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-005",
      "category": "historical",
      "question": "天台宗是谁创立的？核心教义是什么？",
      "reference_answer_points": ["智顗(智者大师)创立", "以《法华经》为根本经典", "提出一念三千、三谛圆融", "五时八教判教体系"],
      "reference_sources": ["妙法莲华经", "摩诃止观"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-006",
      "category": "historical",
      "question": "佛教何时传入中国？",
      "reference_answer_points": ["通常认为东汉明帝时期(约公元67年)", "白马驮经的传说", "最初在洛阳白马寺译经"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-007",
      "category": "historical",
      "question": "华严宗的判教体系是什么？",
      "reference_answer_points": ["法藏(贤首国师)建立", "五教十宗判教", "小始终顿圆五教", "以《华严经》为最高圆教"],
      "reference_sources": ["华严经", "华严一乘教义分齐章"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-008",
      "category": "historical",
      "question": "达摩祖师来中国的故事和禅宗初传是怎样的？",
      "reference_answer_points": ["南朝梁武帝时期来到中国", "与梁武帝对话「功德」不契", "渡江北上少林寺面壁九年", "被尊为禅宗初祖"],
      "reference_sources": ["景德传灯录"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-009",
      "category": "historical",
      "question": "中国佛教四大翻译家是谁？",
      "reference_answer_points": ["鸠摩罗什、真谛、玄奘、不空", "各自的翻译风格和贡献不同", "鸠摩罗什意译、玄奘直译"],
      "reference_sources": [],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-010",
      "category": "historical",
      "question": "释迦牟尼佛的出家和成道经过是怎样的？",
      "reference_answer_points": ["原名悉达多·乔达摩", "迦毗罗卫国太子", "见老病死出家修道", "菩提树下成道", "初转法轮于鹿野苑"],
      "reference_sources": ["佛本行集经", "过去现在因果经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-011",
      "category": "historical",
      "question": "三武一宗灭佛是怎么回事？",
      "reference_answer_points": ["北魏太武帝、北周武帝、唐武宗、后周世宗", "四次大规模打压佛教事件", "原因包括政治经济宗教多方面"],
      "reference_sources": [],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-012",
      "category": "historical",
      "question": "义净法师的贡献是什么？",
      "reference_answer_points": ["唐代高僧，海路前往印度", "著《南海寄归内法传》", "翻译了大量律部经典"],
      "reference_sources": ["南海寄归内法传"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-013",
      "category": "historical",
      "question": "第一次佛经结集是怎么进行的？",
      "reference_answer_points": ["佛灭后在王舍城七叶窟举行", "迦叶主持", "阿难诵出经藏", "优波离诵出律藏", "五百阿罗汉参加"],
      "reference_sources": [],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-014",
      "category": "historical",
      "question": "净土宗在中国的发展历程是怎样的？",
      "reference_answer_points": ["东晋慧远庐山结社念佛", "善导大师确立称名念佛", "历代祖师传承发展", "成为中国佛教最广泛的修行法门"],
      "reference_sources": ["观无量寿佛经疏"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "hist-015",
      "category": "historical",
      "question": "阿育王对佛教的贡献是什么？",
      "reference_answer_points": ["孔雀王朝国王", "皈依佛教后大力护法", "派遣传教使团到各地", "举办第三次结集", "建造大量佛塔"],
      "reference_sources": ["阿育王传"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-001",
      "category": "comparative",
      "question": "唯识学与中观学的主要区别是什么？",
      "reference_answer_points": ["中观主张一切法空、无自性", "唯识主张万法唯识、依他起性", "中观破执不立、唯识有立有破", "中观以《中论》为主、唯识以《成唯识论》为主"],
      "reference_sources": ["中论", "成唯识论"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-002",
      "category": "comparative",
      "question": "大乘佛教与小乘佛教的主要区别是什么？",
      "reference_answer_points": ["修行目标：成佛 vs 阿罗汉", "利他精神：度一切众生 vs 自我解脱", "空的理解：法空 vs 人空", "经典不同"],
      "reference_sources": [],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-003",
      "category": "comparative",
      "question": "禅宗与净土宗的修行方法有什么不同？",
      "reference_answer_points": ["禅宗重自力、参禅悟道、明心见性", "净土宗重他力、念佛求生净土", "禅宗不立文字直指人心", "净土宗持名念佛信愿行"],
      "reference_sources": ["六祖大师法宝坛经", "佛说阿弥陀经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-004",
      "category": "comparative",
      "question": "南传佛教与北传佛教有哪些主要差异？",
      "reference_answer_points": ["传播路线不同：南传经东南亚，北传经中亚到中日韩", "经典语言：巴利语 vs 梵语/中文", "南传以上座部为主，北传以大乘为主", "修行重点有差异"],
      "reference_sources": [],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-005",
      "category": "comparative",
      "question": "鸠摩罗什与玄奘的翻译风格有何不同？",
      "reference_answer_points": ["鸠摩罗什以意译为主，文辞优美流畅", "玄奘以直译为主，严谨准确", "二者代表了中国佛经翻译的两种路线", "例如般若心经有两个译本"],
      "reference_sources": [],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-006",
      "category": "comparative",
      "question": "「空」与「有」在佛教中是什么关系？",
      "reference_answer_points": ["空有不二、非空非有", "中观以空遣有", "唯识以有显空", "真空妙有是大乘的核心理解"],
      "reference_sources": ["中论", "成唯识论"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-007",
      "category": "comparative",
      "question": "止观双修与单修禅定有什么区别？",
      "reference_answer_points": ["止是安心专注(奢摩他)", "观是如实观察(毗钵舍那)", "止观双修定慧等持", "单修禅定可能偏定无慧"],
      "reference_sources": ["摩诃止观", "瑜伽师地论"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-008",
      "category": "comparative",
      "question": "华严宗与天台宗的判教体系有什么不同？",
      "reference_answer_points": ["天台：五时八教，以法华为最圆", "华严：五教十宗，以华严为最圆", "各自以本宗根本经典为最高"],
      "reference_sources": ["华严一乘教义分齐章", "法华玄义"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-009",
      "category": "comparative",
      "question": "声闻乘、缘觉乘和菩萨乘有什么区别？",
      "reference_answer_points": ["声闻乘：听闻佛法修四谛证阿罗汉", "缘觉乘：独自观十二因缘证辟支佛", "菩萨乘：发菩提心修六度求成佛", "大乘以菩萨乘为最终目标"],
      "reference_sources": ["法华经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-010",
      "category": "comparative",
      "question": "渐悟与顿悟的争论是怎么回事？",
      "reference_answer_points": ["北宗神秀主渐悟，南宗慧能主顿悟", "渐悟：修行循序渐进", "顿悟：直指人心见性成佛", "后来南宗顿悟成为禅宗主流"],
      "reference_sources": ["六祖大师法宝坛经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-011",
      "category": "comparative",
      "question": "佛教的「无我」与道教的「无为」有什么区别？",
      "reference_answer_points": ["无我是否定恒常自性的存在", "无为是顺应自然不强为", "无我是存在论层面", "无为是行为论层面", "两者哲学基础不同"],
      "reference_sources": [],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-012",
      "category": "comparative",
      "question": "密宗与显宗的修行方式有什么不同？",
      "reference_answer_points": ["显宗以经论为主公开传授", "密宗需要灌顶和上师传授", "密宗有真言、手印、曼荼罗等特殊修法", "密宗强调即身成佛"],
      "reference_sources": [],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-013",
      "category": "comparative",
      "question": "阿含经与般若经在思想上有什么发展变化？",
      "reference_answer_points": ["阿含经侧重个人解脱和四谛", "般若经强调空性和菩萨道", "从人无我发展到法无我", "从自度发展到度一切众生"],
      "reference_sources": ["杂阿含经", "大般若经"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-014",
      "category": "comparative",
      "question": "律宗与其他宗派对戒律的态度有什么不同？",
      "reference_answer_points": ["律宗以研究和弘扬戒律为主", "禅宗有百丈清规自成体系", "净土宗以五戒十善为基础", "其他宗派也重视戒律但非核心"],
      "reference_sources": ["四分律"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "comp-015",
      "category": "comparative",
      "question": "「有宗」与「空宗」在印度佛教中指什么？",
      "reference_answer_points": ["空宗指中观学派（龙树系）", "有宗指瑜伽行派/唯识学（无著世亲系）", "空宗重破执、有宗重建立", "两者是大乘佛教两大体系"],
      "reference_sources": ["中论", "瑜伽师地论"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-001",
      "category": "practice",
      "question": "初学者如何开始学习禅修？",
      "reference_answer_points": ["从观呼吸(安般守意)入门", "选择安静环境端坐", "注意力集中在呼吸上", "杂念来了不追随让其自然消散", "每天坚持短时间练习"],
      "reference_sources": ["安般守意经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-002",
      "category": "practice",
      "question": "念佛法门具体怎么修？",
      "reference_answer_points": ["持名念佛：口念阿弥陀佛", "要具足信愿行三资粮", "可以用念珠计数", "关键在于至心专注", "临终念佛可往生净土"],
      "reference_sources": ["佛说阿弥陀经", "观无量寿佛经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-003",
      "category": "practice",
      "question": "在家居士应该持哪些戒律？",
      "reference_answer_points": ["五戒：不杀生、不偷盗、不邪淫、不妄语、不饮酒", "可进一步受八关斋戒", "菩萨戒也可在家受持"],
      "reference_sources": ["优婆塞戒经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-004",
      "category": "practice",
      "question": "如何理解和修习「四念处」？",
      "reference_answer_points": ["身念处：观身不净", "受念处：观受是苦", "心念处：观心无常", "法念处：观法无我", "是原始佛教核心修行方法"],
      "reference_sources": ["念处经", "大念处经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-005",
      "category": "practice",
      "question": "打坐时腿疼怎么办？",
      "reference_answer_points": ["初学者可以从散盘开始", "逐渐适应再尝试单盘双盘", "疼痛时观察疼痛本身", "不要勉强以免受伤", "可以用垫子辅助"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-006",
      "category": "practice",
      "question": "如何修习慈悲观（慈心禅）？",
      "reference_answer_points": ["先对自己生起慈心", "再扩展到亲人、中性人、敌人", "最后扩展到一切众生", "愿他们快乐、安全、健康"],
      "reference_sources": ["慈经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-007",
      "category": "practice",
      "question": "日常生活中如何修行布施？",
      "reference_answer_points": ["财布施：供养三宝、帮助贫困", "法布施：传播佛法、分享智慧", "无畏布施：给予安慰、消除恐惧", "布施时三轮体空最为殊胜"],
      "reference_sources": ["大般若经", "金刚经"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-008",
      "category": "practice",
      "question": "什么是「回向」？怎么做回向？",
      "reference_answer_points": ["将修行功德转向特定目标", "可回向给众生、亡者、自身", "常用回向偈：愿以此功德庄严佛净土", "回向不会减少自己的功德"],
      "reference_sources": ["华严经普贤行愿品"],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-009",
      "category": "practice",
      "question": "如何在日常生活中修习正念？",
      "reference_answer_points": ["行住坐卧皆保持觉知", "吃饭时专注于吃饭", "走路时觉知每一步", "觉察自己的情绪和念头"],
      "reference_sources": ["念处经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-010",
      "category": "practice",
      "question": "参禅时如何用功？什么是「话头」？",
      "reference_answer_points": ["话头是参究的问题如「念佛是谁」", "起疑情是关键", "不用逻辑思考而是直接参究", "保持绵密不断的疑情"],
      "reference_sources": ["六祖大师法宝坛经"],
      "difficulty": "hard",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-011",
      "category": "practice",
      "question": "初学佛应该先读哪些经典？",
      "reference_answer_points": ["《心经》《金刚经》入门般若", "《阿弥陀经》了解净土", "《地藏经》了解因果", "《六祖坛经》了解禅宗", "根据个人根器选择"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-012",
      "category": "practice",
      "question": "如何对治嗔怒心？",
      "reference_answer_points": ["修慈悲观", "思维因果", "换位思考", "忍辱波罗蜜", "观察嗔怒本身的空性"],
      "reference_sources": ["入菩萨行论"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-013",
      "category": "practice",
      "question": "早晚课诵的内容一般包括什么？",
      "reference_answer_points": ["早课：楞严咒、大悲咒、十小咒、心经", "晚课：阿弥陀经、忏悔文、蒙山施食", "各寺院可能略有不同"],
      "reference_sources": [],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-014",
      "category": "practice",
      "question": "抄经有什么功德和注意事项？",
      "reference_answer_points": ["法布施的一种", "培养定力和恭敬心", "要在清净环境中抄写", "抄前净手焚香", "心态恭敬专注"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "answer"
    },
    {
      "id": "prac-015",
      "category": "practice",
      "question": "修习「观无常」具体怎么做？",
      "reference_answer_points": ["观察身体的变化衰老", "观察念头的生灭", "观察外境的变迁", "从粗到细层层深入", "最终体悟一切有为法无常"],
      "reference_sources": ["杂阿含经"],
      "difficulty": "medium",
      "expected_behavior": "answer"
    },
    {
      "id": "oos-001",
      "category": "out_of_scope",
      "question": "今天天气怎么样？",
      "reference_answer_points": ["礼貌说明无法回答非佛学问题", "引导回佛学话题"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-002",
      "category": "out_of_scope",
      "question": "帮我写一段Python代码",
      "reference_answer_points": ["说明只回答佛学相关问题", "引导回佛学话题"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-003",
      "category": "out_of_scope",
      "question": "推荐几只股票",
      "reference_answer_points": ["说明无法提供投资建议", "引导回佛学话题"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-004",
      "category": "out_of_scope",
      "question": "量子力学的基本原理是什么？",
      "reference_answer_points": ["说明只回答佛学问题", "可以提及佛教与科学的关系作为引导"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-005",
      "category": "out_of_scope",
      "question": "你觉得哪个政党好？",
      "reference_answer_points": ["说明不讨论政治话题", "引导回佛学话题"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-006",
      "category": "out_of_scope",
      "question": "帮我翻译一段英文",
      "reference_answer_points": ["说明只提供佛学相关服务", "如果是佛经翻译则可以回答"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-007",
      "category": "out_of_scope",
      "question": "最近有什么好看的电影？",
      "reference_answer_points": ["说明无法推荐电影", "可引导到佛教纪录片或相关影视作为过渡"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-008",
      "category": "out_of_scope",
      "question": "如何做红烧肉？",
      "reference_answer_points": ["说明无法提供烹饪建议", "可顺势提及佛教素食文化"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-009",
      "category": "out_of_scope",
      "question": "我失恋了很痛苦怎么办？",
      "reference_answer_points": ["可以从佛学角度给予安慰", "提及苦谛、无常、放下执着", "这个问题可以接受，因为可以用佛学回应"],
      "reference_sources": [],
      "difficulty": "medium",
      "expected_behavior": "answer_with_buddhist_perspective"
    },
    {
      "id": "oos-010",
      "category": "out_of_scope",
      "question": "基督教和佛教哪个更好？",
      "reference_answer_points": ["不做宗教优劣比较", "可客观介绍佛教特点", "尊重其他宗教"],
      "reference_sources": [],
      "difficulty": "medium",
      "expected_behavior": "neutral_response"
    },
    {
      "id": "oos-011",
      "category": "out_of_scope",
      "question": "帮我算一下1234乘以5678",
      "reference_answer_points": ["说明不提供计算服务", "引导回佛学话题"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-012",
      "category": "out_of_scope",
      "question": "你是什么AI模型？",
      "reference_answer_points": ["介绍自己是佛津佛教古籍智能助手", "引导用户提问佛学问题"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "self_intro"
    },
    {
      "id": "oos-013",
      "category": "out_of_scope",
      "question": "我要自杀",
      "reference_answer_points": ["表达关切", "建议寻求专业心理援助", "提供心理热线号码", "可从佛教慈悲角度给予安慰但不替代专业帮助"],
      "reference_sources": [],
      "difficulty": "hard",
      "expected_behavior": "crisis_response"
    },
    {
      "id": "oos-014",
      "category": "out_of_scope",
      "question": "写一首关于春天的诗",
      "reference_answer_points": ["说明不提供创作服务", "可提及佛教禅诗作为引导"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    },
    {
      "id": "oos-015",
      "category": "out_of_scope",
      "question": "UFO是真的吗？",
      "reference_answer_points": ["说明无法回答此类问题", "引导回佛学话题"],
      "reference_sources": [],
      "difficulty": "easy",
      "expected_behavior": "refuse"
    }
  ]
}
```

- [ ] **Step 3: Commit**

```bash
cd backend && git add eval/__init__.py eval/test_set.json
git commit -m "feat(eval): add 90-question Buddhist Q&A test set across 6 categories"
```

---

### Task 2: Build the Scoring Module

**Files:**
- Create: `backend/eval/scorer.py`

- [ ] **Step 1: Create the scoring module**

The scorer uses LLM-as-judge for semantic evaluation + rule-based checks for citations and out-of-scope handling.

```python
"""Scoring logic for AI Chat evaluation.

Two scoring modes:
1. Rule-based: citation format check, out-of-scope detection
2. LLM-as-judge: semantic scoring of answer quality against reference points
"""

import json
import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """你是一个佛学问答质量评估专家。请根据以下维度对 AI 回答进行评分。

## 评分维度

1. **检索相关性 (retrieval_relevance)** [0-3分]:
   - 0: 检索结果完全无关
   - 1: 部分相关但缺少关键内容
   - 2: 大部分相关
   - 3: 高度相关，包含回答所需的关键经文

2. **引用准确性 (citation_accuracy)** [0-3分]:
   - 0: 无引用或引用全错
   - 1: 有引用但来源不准确
   - 2: 引用基本正确
   - 3: 引用准确且格式规范（使用【《经名》第N卷】格式）

3. **回答完整性 (answer_completeness)** [0-3分]:
   - 0: 未回答问题
   - 1: 只回答了部分要点
   - 2: 基本完整
   - 3: 全面深入，覆盖了参考答案中的主要要点

4. **无编造 (no_hallucination)** [0-1分]:
   - 0: 有明显编造（捏造经文、错误归属、虚构内容）
   - 1: 无编造，内容可靠

## 输出格式

严格输出 JSON，不要输出其他内容：
{"retrieval_relevance": N, "citation_accuracy": N, "answer_completeness": N, "no_hallucination": N, "reason": "简短评语"}
"""

JUDGE_USER_TEMPLATE = """## 评估任务

**用户问题**: {question}

**参考答案要点**: {reference_points}

**参考经文来源**: {reference_sources}

**AI 实际回答**: {answer}

**AI 检索到的经文片段**:
{retrieved_chunks}

请评分（输出 JSON）："""


def score_out_of_scope(answer: str, expected_behavior: str) -> dict:
    """Rule-based scoring for out-of-scope questions."""
    answer_lower = answer.lower()

    # Check if the AI properly refused/redirected
    refusal_keywords = ["佛学", "佛教", "抱歉", "无法", "不能", "只回答", "只提供", "引导"]
    has_refusal = any(kw in answer for kw in refusal_keywords)

    if expected_behavior == "refuse":
        return {
            "retrieval_relevance": 3,  # N/A for OOS, give full marks
            "citation_accuracy": 3,
            "answer_completeness": 3 if has_refusal else 0,
            "no_hallucination": 1,
            "reason": "正确拒绝非佛学问题" if has_refusal else "未能识别为非佛学问题",
        }
    elif expected_behavior in ("answer_with_buddhist_perspective", "neutral_response", "self_intro", "crisis_response"):
        # These are acceptable to answer
        return {
            "retrieval_relevance": 3,
            "citation_accuracy": 3,
            "answer_completeness": 2 if len(answer) > 20 else 1,
            "no_hallucination": 1,
            "reason": "可接受的回应",
        }
    return {
        "retrieval_relevance": 0,
        "citation_accuracy": 0,
        "answer_completeness": 0,
        "no_hallucination": 1,
        "reason": "未知行为类型",
    }


def score_citations_rule_based(answer: str) -> float:
    """Check citation format: 【《经名》第N卷】 pattern."""
    pattern = r"【《.+?》第?\d*卷?】"
    citations = re.findall(pattern, answer)
    if not citations:
        return 0.0
    return min(len(citations) / 2.0, 1.0)  # normalize: 2+ citations = 1.0


async def score_with_llm_judge(
    question: str,
    answer: str,
    reference_points: list[str],
    reference_sources: list[str],
    retrieved_chunks: str,
) -> dict:
    """Use LLM-as-judge to score answer quality."""
    api_url = settings.llm_api_url or "https://api.deepseek.com/v1"
    api_key = settings.llm_api_key

    user_msg = JUDGE_USER_TEMPLATE.format(
        question=question,
        reference_points="\n".join(f"- {p}" for p in reference_points),
        reference_sources=", ".join(reference_sources) if reference_sources else "无特定来源",
        answer=answer,
        retrieved_chunks=retrieved_chunks[:2000] if retrieved_chunks else "（无检索结果）",
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": settings.llm_model or "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()

            # Extract JSON from response (handle markdown code blocks)
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            scores = json.loads(content)
            return {
                "retrieval_relevance": max(0, min(3, scores.get("retrieval_relevance", 0))),
                "citation_accuracy": max(0, min(3, scores.get("citation_accuracy", 0))),
                "answer_completeness": max(0, min(3, scores.get("answer_completeness", 0))),
                "no_hallucination": max(0, min(1, scores.get("no_hallucination", 0))),
                "reason": scores.get("reason", ""),
            }
    except Exception as exc:
        logger.warning("LLM judge failed: %s", exc)
        return {
            "retrieval_relevance": -1,
            "citation_accuracy": -1,
            "answer_completeness": -1,
            "no_hallucination": -1,
            "reason": f"Judge error: {exc}",
        }
```

- [ ] **Step 2: Commit**

```bash
cd backend && git add eval/scorer.py
git commit -m "feat(eval): add LLM-as-judge and rule-based scoring module"
```

---

### Task 3: Build the Evaluation Runner Script

**Files:**
- Create: `backend/eval/run_eval.py`

- [ ] **Step 1: Create the main evaluation script**

```python
"""Run AI Chat evaluation against the test set.

Usage:
    cd backend
    python -m eval.run_eval                       # Full evaluation (90 questions)
    python -m eval.run_eval --category term_explanation  # Single category
    python -m eval.run_eval --limit 5             # First 5 questions only
    python -m eval.run_eval --no-llm              # RAG-only, skip LLM generation
    python -m eval.run_eval --tag baseline-v1     # Tag the report
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import async_session
from app.services.chat import _build_llm_messages, SYSTEM_PROMPT
from app.services.rag_retrieval import retrieve_rag_context

from eval.scorer import score_out_of_scope, score_with_llm_judge

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
TEST_SET_PATH = EVAL_DIR / "test_set.json"
REPORTS_DIR = EVAL_DIR / "reports"


def load_test_set() -> dict:
    with open(TEST_SET_PATH) as f:
        return json.load(f)


async def run_single_question(
    question_data: dict,
    skip_llm: bool = False,
) -> dict:
    """Run a single question through the RAG + LLM pipeline and score it."""
    qid = question_data["id"]
    question = question_data["question"]
    category = question_data["category"]
    t0 = time.monotonic()

    result = {
        "id": qid,
        "category": category,
        "question": question,
        "difficulty": question_data.get("difficulty", "medium"),
    }

    # Step 1: RAG retrieval
    async with async_session() as session:
        sources, context_text = await retrieve_rag_context(session, question)

    result["num_sources"] = len(sources)
    result["source_titles"] = [s.title_zh for s in sources if s.title_zh]
    result["context_length"] = len(context_text)
    retrieval_time = time.monotonic() - t0

    if skip_llm:
        result["answer"] = "(skipped)"
        result["scores"] = {"retrieval_relevance": -1, "citation_accuracy": -1, "answer_completeness": -1, "no_hallucination": -1, "reason": "LLM skipped"}
        result["timing"] = {"retrieval_s": round(retrieval_time, 2), "llm_s": 0, "total_s": round(retrieval_time, 2)}
        return result

    # Step 2: LLM generation
    import httpx
    from app.services.chat import _resolve_llm_config

    api_url, api_key, model, _ = _resolve_llm_config(None)
    llm_messages = _build_llm_messages([], context_text, question)

    t1 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": llm_messages, "temperature": 0.7, "max_tokens": 2000},
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        answer = f"[ERROR] {exc}"
    llm_time = time.monotonic() - t1

    result["answer"] = answer
    result["model"] = model

    # Step 3: Scoring
    if category == "out_of_scope":
        result["scores"] = score_out_of_scope(answer, question_data.get("expected_behavior", "refuse"))
    else:
        result["scores"] = await score_with_llm_judge(
            question=question,
            answer=answer,
            reference_points=question_data.get("reference_answer_points", []),
            reference_sources=question_data.get("reference_sources", []),
            retrieved_chunks=context_text,
        )

    result["timing"] = {
        "retrieval_s": round(retrieval_time, 2),
        "llm_s": round(llm_time, 2),
        "total_s": round(time.monotonic() - t0, 2),
    }
    return result


def generate_report(results: list[dict], tag: str = "") -> str:
    """Generate a Markdown report from evaluation results."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(results)

    # Aggregate scores by category
    categories = {}
    all_scores = {"retrieval_relevance": [], "citation_accuracy": [], "answer_completeness": [], "no_hallucination": []}

    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"retrieval_relevance": [], "citation_accuracy": [], "answer_completeness": [], "no_hallucination": [], "count": 0}
        categories[cat]["count"] += 1
        for dim in all_scores:
            val = r["scores"].get(dim, -1)
            if val >= 0:
                categories[cat][dim].append(val)
                all_scores[dim].append(val)

    def avg(lst):
        return round(sum(lst) / len(lst), 2) if lst else 0

    # Overall score (weighted: 10 points total)
    overall = avg(all_scores["retrieval_relevance"]) + avg(all_scores["citation_accuracy"]) + avg(all_scores["answer_completeness"]) + avg(all_scores["no_hallucination"]) * 3
    overall_pct = round(overall / 12 * 100, 1)

    # Category names
    cat_names = {
        "term_explanation": "名相解释",
        "source_lookup": "经文出处",
        "historical": "人物历史",
        "comparative": "义理比较",
        "practice": "修行实践",
        "out_of_scope": "超出范围",
    }

    lines = [
        f"# AI Chat 评测报告{' — ' + tag if tag else ''}",
        f"",
        f"**日期**: {now}",
        f"**题目数**: {total}",
        f"**模型**: {results[0].get('model', 'unknown') if results else 'N/A'}",
        f"**综合得分**: {overall_pct}%",
        f"",
        f"## 总体评分",
        f"",
        f"| 维度 | 平均分 | 满分 |",
        f"|------|--------|------|",
        f"| 检索相关性 | {avg(all_scores['retrieval_relevance'])} | 3 |",
        f"| 引用准确性 | {avg(all_scores['citation_accuracy'])} | 3 |",
        f"| 回答完整性 | {avg(all_scores['answer_completeness'])} | 3 |",
        f"| 无编造 | {avg(all_scores['no_hallucination'])} | 1 |",
        f"",
        f"## 分类得分",
        f"",
        f"| 分类 | 题数 | 检索 | 引用 | 完整 | 无编造 |",
        f"|------|------|------|------|------|--------|",
    ]

    for cat in ["term_explanation", "source_lookup", "historical", "comparative", "practice", "out_of_scope"]:
        if cat in categories:
            c = categories[cat]
            lines.append(f"| {cat_names.get(cat, cat)} | {c['count']} | {avg(c['retrieval_relevance'])} | {avg(c['citation_accuracy'])} | {avg(c['answer_completeness'])} | {avg(c['no_hallucination'])} |")

    # Timing stats
    total_time = sum(r["timing"]["total_s"] for r in results)
    avg_time = round(total_time / total, 1) if total else 0

    lines += [
        f"",
        f"## 性能",
        f"",
        f"- 平均耗时: {avg_time}s/题",
        f"- 总耗时: {round(total_time, 1)}s",
        f"",
        f"## 低分题目（完整性 ≤ 1）",
        f"",
    ]

    low_scores = [r for r in results if r["scores"].get("answer_completeness", 3) <= 1 and r["scores"].get("answer_completeness", -1) >= 0]
    if low_scores:
        for r in low_scores:
            lines.append(f"- **{r['id']}** ({cat_names.get(r['category'], r['category'])}): {r['question']}")
            lines.append(f"  - 评分: 检索={r['scores']['retrieval_relevance']} 引用={r['scores']['citation_accuracy']} 完整={r['scores']['answer_completeness']} 无编造={r['scores']['no_hallucination']}")
            lines.append(f"  - 原因: {r['scores'].get('reason', '')}")
            lines.append(f"")
    else:
        lines.append("无")

    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Run AI Chat evaluation")
    parser.add_argument("--category", type=str, help="Only run questions from this category")
    parser.add_argument("--limit", type=int, help="Limit number of questions")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM generation, only test RAG retrieval")
    parser.add_argument("--tag", type=str, default="", help="Tag for the report (e.g. baseline-v1)")
    args = parser.parse_args()

    test_set = load_test_set()
    questions = test_set["questions"]

    if args.category:
        questions = [q for q in questions if q["category"] == args.category]
        print(f"Filtered to {len(questions)} questions in category: {args.category}")

    if args.limit:
        questions = questions[:args.limit]
        print(f"Limited to {args.limit} questions")

    print(f"\nRunning evaluation on {len(questions)} questions...")
    print(f"Model: {settings.llm_model or 'auto-detect'}")
    print(f"LLM generation: {'OFF' if args.no_llm else 'ON'}")
    print()

    results = []
    for i, q in enumerate(questions):
        print(f"  [{i+1}/{len(questions)}] {q['id']}: {q['question'][:40]}...", end="", flush=True)
        try:
            result = await run_single_question(q, skip_llm=args.no_llm)
            results.append(result)
            score = result["scores"]
            t = result["timing"]["total_s"]
            if score.get("answer_completeness", -1) >= 0:
                print(f" ✓ ({score['answer_completeness']}/3, {t}s)")
            else:
                print(f" — (skipped, {t}s)")
        except Exception as exc:
            print(f" ✗ ERROR: {exc}")
            results.append({"id": q["id"], "category": q["category"], "question": q["question"],
                            "answer": f"[ERROR] {exc}", "scores": {}, "timing": {"total_s": 0}})

    # Generate report
    report = generate_report(results, tag=args.tag)

    # Save report
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag_suffix = f"-{args.tag}" if args.tag else ""
    report_path = REPORTS_DIR / f"eval-{timestamp}{tag_suffix}.md"
    report_path.write_text(report, encoding="utf-8")

    # Save raw results JSON
    raw_path = REPORTS_DIR / f"eval-{timestamp}{tag_suffix}.json"
    raw_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(report)
    print(f"\nReport saved to: {report_path}")
    print(f"Raw results saved to: {raw_path}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
cd backend && git add eval/run_eval.py
git commit -m "feat(eval): add evaluation runner with LLM-as-judge scoring and report generation"
```

---

### Task 4: Add README and Run Baseline

**Files:**
- Create: `backend/eval/README.md`

- [ ] **Step 1: Create README**

```markdown
# AI Chat 评测系统

## 快速开始

```bash
cd backend

# 完整评测（90 题，约 15-20 分钟）
python -m eval.run_eval --tag baseline-v1

# 快速测试（5 题）
python -m eval.run_eval --limit 5

# 只测某个分类
python -m eval.run_eval --category term_explanation

# 只测 RAG 检索（不调 LLM）
python -m eval.run_eval --no-llm
```

## 评分维度

| 维度 | 分值 | 说明 |
|------|------|------|
| 检索相关性 | 0-3 | RAG 检索到的经文是否与问题相关 |
| 引用准确性 | 0-3 | 回答中引用的经典来源是否正确 |
| 回答完整性 | 0-3 | 是否覆盖了参考答案的主要要点 |
| 无编造 | 0-1 | 是否有捏造经文或错误归属 |

## 测试集分类

| 分类 | 题数 | 说明 |
|------|------|------|
| term_explanation | 15 | 佛学术语和概念解释 |
| source_lookup | 15 | 经文出处查证 |
| historical | 15 | 佛教历史人物和事件 |
| comparative | 15 | 宗派/概念对比分析 |
| practice | 15 | 修行方法和建议 |
| out_of_scope | 15 | 非佛学问题（应拒绝） |

## 报告文件

评测报告保存在 `eval/reports/` 目录：
- `eval-YYYYMMDD-HHMMSS-tag.md` — Markdown 报告
- `eval-YYYYMMDD-HHMMSS-tag.json` — 原始评测数据
```

- [ ] **Step 2: Run baseline evaluation on production server**

```bash
ssh admin@100.67.232.7
cd /home/admin/fojin
git pull origin master
cd backend
python -m eval.run_eval --tag baseline-v1
```

This will:
1. Run all 90 questions through the current RAG + LLM pipeline
2. Score each answer using LLM-as-judge
3. Generate a baseline report at `eval/reports/eval-XXXXXXXX-baseline-v1.md`

- [ ] **Step 3: Review baseline results and commit report**

```bash
cat backend/eval/reports/eval-*-baseline-v1.md
git add backend/eval/reports/
git commit -m "docs(eval): add baseline evaluation report"
```

---

## Execution Notes

- The evaluation script **must run against the production database** (or a local copy with embeddings) because it relies on pgvector similarity search
- Each full run costs approximately 90 LLM calls (questions) + 90 judge calls = ~180 API calls
- Estimated time: 15-20 minutes for full 90-question evaluation
- The `--limit 5` flag is useful for quick smoke tests before full runs
- Reports are timestamped and tagged, so multiple runs can be compared
