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
    id: str           # stable key sent from frontend (e.g. "deepseek:v4-pro")
    provider: str     # matches PROVIDER_URLS keys in chat.py
    model: str        # actual API model id
    label: str        # display name for dropdown
    description: str  # short tooltip text
    vision: bool


# Order matters — first entry is the default when no localStorage value exists.
# 每个模型商只保留最新的一个旗舰模型。
CATALOG: list[ModelOption] = [
    ModelOption("deepseek:v4-pro", "deepseek", "deepseek-v4-pro",
                "DeepSeek V4 Pro", "旗舰模型，复杂推理", False),
    ModelOption("dashscope:qwen3.6-plus", "dashscope", "qwen3.6-plus",
                "通义千问 Qwen3.6 Plus", "阿里最新文本旗舰", False),
    ModelOption("moonshot:kimi-k2.6", "moonshot", "kimi-k2.6",
                "Kimi K2.6", "Moonshot 最新旗舰", False),
    ModelOption("zhipu:glm-5.1", "zhipu", "glm-5.1",
                "智谱 GLM-5.1", "744B 参数，编码与推理强", False),
]

CATALOG_BY_ID = {opt.id: opt for opt in CATALOG}

DEFAULT_MODEL_ID = "deepseek:v4-pro"
