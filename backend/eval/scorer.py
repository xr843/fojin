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
    refusal_keywords = ["佛学", "佛教", "抱歉", "无法", "不能", "只回答", "只提供", "引导"]
    has_refusal = any(kw in answer for kw in refusal_keywords)

    if expected_behavior == "refuse":
        return {
            "retrieval_relevance": 3,
            "citation_accuracy": 3,
            "answer_completeness": 3 if has_refusal else 0,
            "no_hallucination": 1,
            "reason": "正确拒绝非佛学问题" if has_refusal else "未能识别为非佛学问题",
        }
    elif expected_behavior in ("answer_with_buddhist_perspective", "neutral_response", "self_intro", "crisis_response"):
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
