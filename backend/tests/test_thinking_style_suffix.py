"""思考方式后缀：砍掉推理里的重复劳动（写草稿、复述规则），不动引文核对。

2026-10-15 同窗配对 eval（90 题 × 2 臂、temperature 0、同时段并行，
backend/eval/model_pair_eval.py）：
  对照（线上原样）  首字中位 38.0s / p90 79.9s，推理 3,533 字，逐字 90.5%，卷号 94.2%
  加本后缀          首字中位 25.7s / p90 60.7s，推理 2,126 字，逐字 91.9%，卷号 93.2%
  配对：逐字 5:6、卷号 7:7（p=1.0），引文总数 268→292，零截断。
动机来自 10 道题的完整思考文本：约四成是在思考里先写一遍回答草稿，另有大量
逐条复述格式规则 —— 两者都是纯重复，与「逐字核对引文」无关。

边界与钉死（同 test_citation_discipline_suffix）：
  1. 只加在普通 RAG 问答路径，且在引文纪律后缀**之后**、系统提示词末尾（eval 注入位置）；
  2. 祖师 / meta / 阅读页不带 —— 未测过，不扩散；
  3. 文字与 eval 逐字相同 —— 改文字等于作废 eval 结论。
"""

from app.services.prompt_builder import (
    CITATION_DISCIPLINE_SUFFIX,
    THINKING_STYLE_SUFFIX,
    _build_llm_messages,
)


def _system_of(msgs: list[dict]) -> str:
    assert msgs[0]["role"] == "system"
    return msgs[0]["content"]


def test_plain_rag_question_gets_it_after_the_discipline_suffix_at_the_end():
    system = _system_of(_build_llm_messages([], "【系统自动检索】……", "「般若」和智慧有什么不同？"))
    assert system.endswith(CITATION_DISCIPLINE_SUFFIX + THINKING_STYLE_SUFFIX), (
        f"顺序必须是 …引文纪律 → 思考方式（eval 的注入位置）；实际结尾: …{system[-120:]!r}"
    )


def test_wording_is_pinned_to_the_evaled_text():
    assert THINKING_STYLE_SUFFIX == (
        "\n\n## 思考方式\n"
        "思考只做三件事：确认出处与卷号、逐字核对要引用的原文是否出现在检索片段中、排定要点。"
        "不要在思考中写出完整的回答草稿，也不要逐条复述或自查以上格式规则——引文核对完成后直接作答。"
    )


def test_meta_question_does_not_get_it():
    assert THINKING_STYLE_SUFFIX not in _system_of(_build_llm_messages([], "", "你是谁"))


def test_master_path_does_not_get_it():
    msgs = _build_llm_messages([], "【系统自动检索】……", "如何修行？", master_id="huineng")
    assert THINKING_STYLE_SUFFIX not in _system_of(msgs)


def test_reader_path_does_not_get_it():
    msgs = _build_llm_messages(
        [], "", "这一段什么意思？",
        reading_context={"title": "般若波羅蜜多心經", "juan_num": 1,
                         "selected_text": None, "page_content": "觀自在菩薩……"},
    )
    assert THINKING_STYLE_SUFFIX not in _system_of(msgs)
