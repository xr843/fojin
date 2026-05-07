"""Curated list of LLMs the user can choose from in the chat dropdown.

This is a small, opinionated subset of PROVIDER_DEFAULT_MODELS in
chat.py — those are server-side defaults; this catalog is what the
frontend dropdown shows. Each entry maps a stable `id` to a
(provider, model) pair plus UI metadata.

vision: True means the model accepts image inputs (used by PR-C image
upload to gate routing — for PR-A this is just data).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelOption:
    id: str           # stable key sent from frontend (e.g. "deepseek:v4-flash")
    provider: str     # matches PROVIDER_URLS keys in chat.py
    model: str        # actual API model id
    label: str        # display name for dropdown
    description: str  # short tooltip text
    vision: bool


# Order matters — first entry is the default when no localStorage value exists.
CATALOG: list[ModelOption] = [
    ModelOption("deepseek:v4-flash", "deepseek", "deepseek-v4-flash",
                "DeepSeek V4 Flash", "经济快速，日常问答首选", False),
    ModelOption("deepseek:v4-pro", "deepseek", "deepseek-v4-pro",
                "DeepSeek V4 Pro", "1.6T 参数旗舰，复杂推理（5-31 前 75% 折扣）", False),
    ModelOption("dashscope:qwen3.6-plus", "dashscope", "qwen3.6-plus",
                "通义千问 Qwen3.6 Plus", "阿里最新文本旗舰", False),
    ModelOption("dashscope:qwen3-vl-flash", "dashscope", "qwen3-vl-flash-2026-01-22",
                "通义千问 Qwen3-VL Flash", "支持图片识别（PR-C 启用）", True),
    ModelOption("moonshot:kimi-k2.6", "moonshot", "kimi-k2.6",
                "Kimi K2.6", "Moonshot 原生多模态，支持图片", True),
    ModelOption("zhipu:glm-5.1", "zhipu", "glm-5.1",
                "智谱 GLM-5.1", "744B 参数，编码与推理强", False),
    ModelOption("zhipu:glm-4.6v", "zhipu", "glm-4.6v",
                "智谱 GLM-4.6V", "智谱视觉模型，支持图片", True),
]

CATALOG_BY_ID = {opt.id: opt for opt in CATALOG}

DEFAULT_MODEL_ID = "deepseek:v4-flash"
