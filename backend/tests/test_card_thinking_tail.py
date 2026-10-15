"""卡片题（热门问题）的作答提示：贴在卡片模板**末尾**，砍掉推理里的草稿。

为什么不靠系统提示里的 THINKING_STYLE_SUFFIX：卡片模板把「分三层 / 四个角度 /
附引用」写在用户消息里，结构要求离生成更近，系统提示末尾那句被盖住 —— 抓下的
卡片题推理里仍有最多 39% 的答案句子先写过一遍草稿。

2026-10-15 同窗配对（40 张卡片，四类各 10，temperature 0）：
  系统提示里再加一段卡片专用说明  → 推理 5,570→5,616 字，无效（未上线）
  本提示贴在卡片模板末尾          → 首字中位 77.6s→53.6s、p90 126.2→83.4s，
                                     推理 6,028→4,095 字，32/40 题更快（p<0.001）；
                                     逐字 93.1%→100%（配对 0:2）、卷号 88.0%→92.0%（3:6），
                                     引文 162→157，有引用答案 33→30。
"""

import inspect

from app.services import chat
from app.services.prompt_builder import CARD_THINKING_TAIL, card_llm_message


def test_tail_is_appended_after_the_template():
    tmpl = "【任务】用现代白话解释以下内容\n【原文】贪、瞋、痴三毒\n请分三层回答"
    out = card_llm_message(tmpl)
    assert out.startswith(tmpl)
    assert out.endswith(CARD_THINKING_TAIL)


def test_wording_is_pinned_to_the_evaled_text():
    """改一个字就作废 2026-10-15 那次 eval，改前必须重跑。"""
    assert CARD_THINKING_TAIL == (
        "\n\n（作答提示：思考中只确认出处、逐字核对要引用的原文、排定要点；"
        "不要在思考中先写回答草稿或表格，核对完直接作答。）"
    )


def test_chat_card_path_uses_it():
    """卡片模板进入 LLM 之前必须经过 card_llm_message —— 只有卡片路径，普通提问不带。"""
    src = inspect.getsource(chat._prepare_chat)
    assert "llm_message_override = card_llm_message(hq[1])" in src
    assert src.count("card_llm_message(") == 1
