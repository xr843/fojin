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
#
# DeepSeek 是这条规则唯一的例外，且是有意的：flash 不是第二个旗舰，而是同一代
# 模型的轻快档 —— 上下文（1M）与最大输出（384K）和 pro 完全相同，价格是 1/3
# （输入 1 vs 3、输出 2 vs 6 元/百万 token），并发上限 2500 vs 500，两者都支持
# 思考模式。放进目录是让人能自己选着比，默认仍是 pro：换默认要先用
# backend/eval 的 90 题量出引用准确性与幻觉率的差，没数据之前不动。
CATALOG: list[ModelOption] = [
    ModelOption("deepseek:v4-pro", "deepseek", "deepseek-v4-pro",
                "DeepSeek V4 Pro", "旗舰模型，复杂推理", False),
    # 描述里不提价格：这是给读者选模型用的提示，价格是运营侧的事，摆在选择器里
    # 只会让人以为便宜的那个"缩水"了。实际上两者规格相同，所以说明这一点最有用。
    # 也不写"更快"——名字里的 Flash 已经是厂商的定位，而我们没有实测数据支撑。
    ModelOption("deepseek:v4-flash", "deepseek", "deepseek-v4-flash",
                "DeepSeek V4 Flash", "同代轻量档，上下文同为 1M", False),
    # 这三家都只对自带 Key 的用户可选（平台没有配它们的 Key）。上游模型名写错的
    # 后果不是"退回默认"，而是那位用户直接吃一个 model not found —— 所以每次更新
    # 都以厂商官方模型列表为准，不采信二手文章。2026-07-31 核对：
    #   · qwen3.6-plus 已不在阿里的模型列表里 —— 沿用 plus 档只升版本，不改档位：
    #     换成 max 会悄悄抬高自带 Key 用户的花费，而这次要做的是同步版本
    #   · kimi-k2.6 仍可调用但已非最新；k3 起上下文到 1M
    #   · glm-5.1 仍在，但 5.2 才是当前旗舰（1M 上下文）
    ModelOption("dashscope:qwen3.7-plus", "dashscope", "qwen3.7-plus",
                "通义千问 Qwen3.7 Plus", "阿里最新一代主力档", False),
    ModelOption("moonshot:kimi-k3", "moonshot", "kimi-k3",
                "Kimi K3", "Moonshot 最新旗舰，上下文 1M", False),
    ModelOption("zhipu:glm-5.2", "zhipu", "glm-5.2",
                "智谱 GLM-5.2", "智谱最新旗舰，上下文 1M", False),
    # 2026-08-01 从火山方舟官方模型列表页核对（该站是 JS 渲染，WebFetch 只能拿到
    # 导航骨架，必须用浏览器打开才读得到表格）。"推荐模型"一栏里的旗舰就是它。
    # 没取 doubao-seed-evolving：它上下文更大（1024k）但是**滚动别名**，模型会在
    # 用户脚下悄悄更换——对一个把答案真实性当最高准则的项目，钉死版本更稳妥。
    ModelOption("doubao:seed-2-1-pro", "doubao", "doubao-seed-2-1-pro-260628",
                "豆包 Seed 2.1 Pro", "字节最新旗舰，上下文 256k", False),
    # 国际三家。同样只对自带 Key 的用户可选。
    # 名单能放开加，是因为选择器只列当前真能用的模型 —— 加一个厂商不会让下拉变长。
    ModelOption("openai:gpt-5.6-sol", "openai", "gpt-5.6-sol",
                "GPT-5.6 Sol", "OpenAI 旗舰，复杂推理", False),
    ModelOption("anthropic:claude-opus-5", "anthropic", "claude-opus-5",
                "Claude Opus 5", "Anthropic 旗舰", False),
    # Gemini 3 系列没有 Pro 档（官方文档确认），最新的稳定版就是 3.6 Flash；
    # 3.1 Pro 尚是 preview，不进目录。
    ModelOption("gemini:gemini-3.6-flash", "gemini", "gemini-3.6-flash",
                "Gemini 3.6 Flash", "Google 最新稳定版", False),
]

CATALOG_BY_ID = {opt.id: opt for opt in CATALOG}

DEFAULT_MODEL_ID = "deepseek:v4-pro"
