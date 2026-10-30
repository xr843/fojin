"""中文作答字形指令：只在阅读器路径追加，ui_lang 只决定中文作答的简/繁。

背景：后端此前不知道用户界面语言，系统提示规则 6「使用用户的语言回答」
让模型按上下文主体字形作答——阅读器模式下页面经文与检索片段都是繁体，
简体用户会收到繁体回答（fojin.app 实测）。前端现经 ChatRequest.ui_lang
把界面语言传进来，本文件钉住注入位置与文字边界：

  1. 只在带 reading_context 的请求里追加（维护者 PR #1376 同时段配对评测：
     /chat 主路径不加指令时 90 题中 89 题已简体回答，加了反而逐字引用
     95.2%→90.2%、卷号 96.4%→94.3%；问题场景只有阅读器面板——页面原文是繁体）；
  2. 非阅读器路径即使传了 ui_lang，系统提示词也逐字节不变（eval 钉死路径兼容）；
  3. 指令追加在系统提示词**最末尾**（离生成最近的指令服从率最高）；
  4. 指令要求引文原文与【《经名》第N卷】经名保持原始字形，不得转写；
  5. en 不加后缀——作答语言跟提问走，英文界面的中文用户提问应得到中文回答。
"""

from app.schemas.chat import ChatRequest
from app.services.prompt_builder import _build_llm_messages

_READER_CTX = {"title": "般若波羅蜜多心經", "juan_num": 1,
               "selected_text": None, "page_content": "觀自在菩薩……"}


def _system_of(msgs: list[dict]) -> str:
    assert msgs[0]["role"] == "system"
    return msgs[0]["content"]


def _plain(**kwargs) -> str:
    return _system_of(_build_llm_messages([], "【系统自动检索】……", "什么是空性？", **kwargs))


def test_plain_path_ignores_ui_lang():
    """/chat 主路径：传不传 ui_lang 提示词都逐字节不变（维护者评测后的最终边界）。"""
    baseline = _plain()
    for code in (None, "zh", "zh-Hant", "en", "fr"):
        assert _plain(ui_lang=code) == baseline, f"ui_lang={code} 不应改变 /chat 主路径提示词"


def test_reader_path_appends_simplified_directive_at_the_end():
    system = _system_of(_build_llm_messages(
        [], "", "什么是空性？", reading_context=_READER_CTX, ui_lang="zh",
    ))
    assert "中文作答的字形" in system
    assert "简体中文" in system
    # 追加在阅读器要求块之后、系统提示词最末尾
    assert system.endswith(
        "引用相关的注疏或其他经典进行对照\n"
        "\n\n## 中文作答的字形\n"
        "当回答使用中文时（含正文、白话翻译、术语解释和文末的[追问]建议），一律使用简体中文书写；"
        "用哪种语言作答仍跟随用户的提问（规则 6），本指令仅在回答为中文时约束简/繁。"
        "逐字引用经文原文时保持其原始字形（通常为繁体），不得转写、翻译引文本身；"
        "【《经名》第N卷】引用中的经名保持[出处]行的原始写法（通常为繁体）。"
    )


def test_reader_path_appends_traditional_directive():
    system = _system_of(_build_llm_messages(
        [], "", "什麼是空性？", reading_context=_READER_CTX, ui_lang="zh-Hant",
    ))
    assert "繁體中文" in system


def test_reader_path_en_gets_no_directive():
    """en 在阅读器路径也不加：作答语言跟提问走，只约束中文作答的简/繁。"""
    baseline = _system_of(_build_llm_messages([], "", "What is emptiness?", reading_context=_READER_CTX))
    assert _system_of(_build_llm_messages(
        [], "", "What is emptiness?", reading_context=_READER_CTX, ui_lang="en",
    )) == baseline


def test_reader_path_unknown_code_is_ignored():
    baseline = _system_of(_build_llm_messages([], "", "什么是空性？", reading_context=_READER_CTX))
    assert _system_of(_build_llm_messages(
        [], "", "什么是空性？", reading_context=_READER_CTX, ui_lang="fr",
    )) == baseline


def test_master_path_ignores_ui_lang():
    """祖师路径没有 reading_context，属于 /chat 主路径家族：不加指令。"""
    baseline = _system_of(_build_llm_messages([], "【系统自动检索】……", "如何修行？", master_id="huineng"))
    assert _system_of(_build_llm_messages(
        [], "【系统自动检索】……", "如何修行？", master_id="huineng", ui_lang="zh",
    )) == baseline


def test_chat_request_accepts_ui_lang():
    r = ChatRequest(message="hi", ui_lang="zh-Hant")
    assert r.ui_lang == "zh-Hant"
    # 缺省 None —— 旧前端请求不带这个字段也合法
    assert ChatRequest(message="hi").ui_lang is None
