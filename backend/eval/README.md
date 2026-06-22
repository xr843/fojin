# AI Chat 评测 (answer-quality eval)

把"答案质量"从凭感觉变成可度量、可回归。两层评分：

| 层 | 是什么 | 需要什么 | 跑在哪 |
|----|--------|----------|--------|
| **确定性检索指标** | Recall@K / Hit@K / MRR / Precision@K，对照每题黄金来源，繁简折叠匹配经名（+可选卷号） | 只需语料库 DB（不需 LLM） | prod / cron，可做回归门 |
| **LLM-as-judge** | 检索相关性 / 引用准确性 / 回答完整性 / 无编造（语义打分） | DB + LLM key | prod / 人工 |
| **指标逻辑单测** | `retrieval_metrics.py` 的纯函数单测 | 无（纯逻辑） | **CI 自动跑**（`tests/test_retrieval_metrics.py`） |

> 全量 eval 需要 678K 向量的语料库 DB，**无法在 GitHub CI 里跑**。所以：度量工具本身的逻辑由 CI 单测护住；全量 eval + 回归门跑在能连到 prod DB 的地方（cron 最合适）。

## 运行

```bash
cd backend

# 只测检索（不烧 LLM token）——确定性指标只需 DB
python -m eval.run_eval --no-llm

# 全量（含 LLM judge）
python -m eval.run_eval --tag nightly

# 子集 / 单类
python -m eval.run_eval --category source_lookup --limit 5
```

报告写到 `eval/reports/eval-<时间戳>-<tag>.md`（+ 同名 `.json` 原始结果，含每题 `retrieval_metrics`）。

## 回归门（用在 cron）

把上次的原始 `.json` 当基线，本次检索指标若跌超过容差就非零退出：

```bash
python -m eval.run_eval --no-llm \
  --baseline eval/reports/eval-<上次>-baseline.json \
  --fail-on-regression --regression-tolerance 0.02
# 或设绝对下限：
python -m eval.run_eval --no-llm --min-recall5 0.70
```

退出码非零即"质量退化"，cron 里可据此告警（接现有 Telegram bot）。

## 黄金来源 schema（`test_set.json`）

每题可选两种标注，`gold_sources` 优先：

```jsonc
{
  "reference_sources": ["般若波罗蜜多心经"],          // title 级，卷号=任意（LLM judge 也读它）
  "gold_sources": [                                  // 确定性 juan 级，更精确
    {"title": "般若波罗蜜多心经", "juan": 1, "relevance": 3}
  ]
}
```

- 匹配规则：经名经 NFKC + 繁→简 + 去标点 折叠后**相等**（不做包含/别名）；`juan` 为 `null`/缺省时只比经名。
- **加 juan 级黄金前务必核对真实卷数**（多卷经典别猜卷号，留 title 级即可），否则会把回归门搞坏。当前只对单卷经典（心经/金刚经/阿弥陀经/坛经）标了 juan。
- `out_of_scope` 等无黄金来源的题：检索指标记为 `None`，自动从均值里排除。

> ⚠️ **建立首个 baseline 前必须在 prod 核对经名能匹配上**：黄金经名是简体，要和 prod `buddhist_texts.title_zh`（CBETA 繁体规范名）折叠后**精确相等**才算命中。先跑
> `python -m eval.run_eval --no-llm --category source_lookup`，确认有 `gold_sources` 的题 `retrieval_metrics.recall@5 > 0`（**不是 0**）。若为 0，多半是黄金经名与 DB 规范名用词不一致（如缺「佛說」前缀、译本不同），改对再把该次结果存为 baseline——否则会把"标题对不上"的隐性 0 命中固化成基准，回归门形同虚设。

## 文件

- `retrieval_metrics.py` — 确定性指标纯函数（CI 单测覆盖）
- `run_eval.py` — RAG→(LLM)→打分→报告→回归门
- `scorer.py` — LLM-as-judge + out-of-scope 规则评分
- `test_set.json` — 黄金评测集
