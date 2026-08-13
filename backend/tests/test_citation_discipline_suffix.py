"""引文纪律后缀：只加在被 eval 验证过的那条路径上。

2026-08-13 四臂 eval（90 题 × 4 臂、temperature 0、同时段并行）的 D 臂结论：
默认档 + 本后缀，三个忠实度指标齐升（逐字 90.2%→94.7%、卷号 94.4%→98.0%、
全验证 80.6%→84.4%，配对 1:4），延迟同量级，代价是引文总数 −30%。

三条边界与一条钉死：
  1. 普通 RAG 问答必须带后缀，且在系统提示词**末尾**（eval 的注入位置）；
  2. 祖师 / meta / 阅读页三条路径不带 —— 它们没测过，不扩散；
  3. 后缀文字与 eval 逐字相同 —— 改文字等于作废 eval 结论。
"""

from app.services.prompt_builder import (
    CITATION_DISCIPLINE_SUFFIX,
    _build_llm_messages,
)


def _system_of(msgs: list[dict]) -> str:
    assert msgs[0]["role"] == "system"
    return msgs[0]["content"]


def test_plain_rag_question_gets_the_suffix_at_the_end():
    msgs = _build_llm_messages([], "【系统自动检索】……", "「般若」和智慧有什么不同？")
    system = _system_of(msgs)
    assert system.endswith(CITATION_DISCIPLINE_SUFFIX), (
        "后缀必须在系统提示词末尾（与 eval 注入位置一致，且离生成最近的指令"
        f"服从率最高）；实际结尾: …{system[-80:]!r}"
    )


def test_suffix_text_is_pinned_to_the_evaled_wording():
    """改这段文字等于作废 2026-08-13 的四臂 eval，改前必须重跑。"""
    assert "逐字复制" in CITATION_DISCIPLINE_SUFFIX
    assert "宁可少引、不可错引" in CITATION_DISCIPLINE_SUFFIX
    assert "最多引 1 条" in CITATION_DISCIPLINE_SUFFIX


def test_meta_question_does_not_get_the_suffix():
    """meta 路径本来就禁止引用，再加引文纪律是自相矛盾的噪音。"""
    msgs = _build_llm_messages([], "", "你是谁")
    assert CITATION_DISCIPLINE_SUFFIX not in _system_of(msgs)


def test_master_path_does_not_get_the_suffix():
    """祖师问答是另一套提示词家族，D 臂没测过它 —— 不扩散。"""
    msgs = _build_llm_messages([], "【系统自动检索】……", "如何修行？", master_id="huineng")
    assert CITATION_DISCIPLINE_SUFFIX not in _system_of(msgs)


def test_reader_path_does_not_get_the_suffix():
    """阅读页要求围绕页面原文解读引用，与「宁可少引」的取向相反，且未测过。"""
    msgs = _build_llm_messages(
        [], "", "这一段什么意思？",
        reading_context={"title": "般若波羅蜜多心經", "juan_num": 1,
                         "selected_text": None, "page_content": "觀自在菩薩……"},
    )
    assert CITATION_DISCIPLINE_SUFFIX not in _system_of(msgs)
