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

门逻辑版本化在 **`eval/run_regression.sh`**（别再把它只写在 VPS crontab 里——
改 `run_eval` 的 flag/签名时，review 里就能看到这个依赖）。它对照基线、检索指标
跌超过容差就**非零退出**：

```bash
# 在 backend 容器内（cwd /app），对照 eval/reports/baseline.json：
eval/run_regression.sh
# 自定义基线 / 绝对下限 / 容差：
BASELINE=eval/reports/baseline-v2.json MIN_RECALL5=0.30 TOLERANCE=0.03 eval/run_regression.sh
```

prod cron 调用方式（薄包装，Telegram 凭据留在 VPS 不进 repo）：

```bash
cd /home/admin/fojin && docker compose exec -T backend eval/run_regression.sh \
  || curl -s "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" --data-urlencode chat_id="${TG_CHAT}" \
       --data-urlencode text="FoJin 答案质量回归门告警"
```

> 全量 eval 需要 678K 向量的语料库 DB，**CI 跑不了**；门只在能连 prod DB 处跑，
> 而门用到的**指标逻辑**由 CI 单测护住（`test_retrieval_metrics.py` / `test_rag_rerank_merge.py`）。
> 有意提升质量后，用 `python -m eval.run_eval --no-llm --tag baseline` 重新生成基线并存为新 `BASELINE`。

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

## 反馈闭环：让线上失败自动变成评测候选

`test_set.json` 是手工静态集，没有任何东西把线上真实失败喂回来——同一个错误可以一直回归而门测不到。`from_feedback.py` 把两个已入库的失败信号

1. 用户点踩（`chat_messages.feedback == 'down'`），
2. 后台答案质量队列里被判 `bad` 的（`answer_reviews.verdict == 'bad'`，带 `failure_category`）

配上产生该回答的用户问题（复用 `answer_quality._attach_questions` 的同事务同 `created_at` 配对逻辑），产出**候选**：

```bash
# 需要 prod 语料库 DB（chat_messages / answer_reviews 在那里）
python -m eval.from_feedback --window-days 90 --limit 200
# → eval/reports/feedback-candidates-<时间戳>.json
```

**为什么是候选而不是直接进 test_set**：黄金条目需要 `reference_sources` / `reference_answer_points`——即*正确*答案的出处，而一个坏答案按定义不含它。工具只负责浮出"值得加进去的问题"和"观察到的失败证据"，`curate` 块留空由人来填。填之前务必按上面 ⚠️ 的规则核对经名能和 `buddhist_texts.title_zh` 折叠匹配，否则回归门形同虚设。

> 建议做法：这一步跑在能连 prod DB 的地方（cron 或手动），产出的候选文件人工过一遍、补全 `curate`，再挑值得的并进 `test_set.json`。这样 90→200+ 的扩集是"由真实失败驱动"而非凭空想题。

## 文件

- `retrieval_metrics.py` — 确定性指标纯函数（CI 单测覆盖）
- `run_eval.py` — RAG→(LLM)→打分→报告→回归门
- `scorer.py` — LLM-as-judge + out-of-scope 规则评分
- `from_feedback.py` — 线上点踩/后台判坏 → 评测候选（CI 单测 `tests/test_from_feedback.py`）
- `test_set.json` — 黄金评测集
