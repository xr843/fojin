"""/chat 多轮上下文窗口：历史预算与条数上限走配置，且扩窗不放大附件/检索的份额。

背景（2026-10 生产实测）：17.5% 的会话超过 10 条消息，助手回答中位 799 字。
旧预算是总共 6000 token、历史最多 10 条 —— 一段俱舍论研读会话里，模型实际
只看得到约 4 轮之前的讨论，每贴一段新原文就丢一段旧讨论。
"""

from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.prompt_builder import _build_llm_messages, _estimate_tokens

# 生产中位长度：用户提问 ~31 字、助手回答 ~799 字
USER_LEN, ASSISTANT_LEN = 31, 799
# 检索片段：通常几千字，会被截到基础预算剩余部分的 60%
CONTEXT = "藏" * 6000


def _session(n_pairs: int) -> list:
    """n_pairs 轮问答，每条消息带可识别的序号标签（越小越早）。"""
    msgs = []
    for i in range(n_pairs):
        msgs.append(SimpleNamespace(role="user", content=f"<Q{i:02d}>" + "问" * USER_LEN))
        msgs.append(SimpleNamespace(role="assistant", content=f"<A{i:02d}>" + "答" * ASSISTANT_LEN))
    return msgs


def _history_tags(messages: list[dict]) -> list[str]:
    # 首条是 system、末条是本轮 user，中间是带入的历史
    return [m["content"][:5] for m in messages[1:-1]]


@pytest.fixture
def window(monkeypatch):
    def _set(max_input: int, max_messages: int) -> None:
        monkeypatch.setattr(settings, "chat_max_input_tokens", max_input)
        monkeypatch.setattr(settings, "chat_history_max_messages", max_messages)

    return _set


class TestLongSessionCarriesMoreHistory:
    def test_default_window_reaches_past_the_tenth_message(self):
        """默认配置下，15 轮会话里第 10 条之前的讨论（倒数第 11 条起）要进得来。"""
        history = _session(15)
        tags = _history_tags(_build_llm_messages(history, CONTEXT, "下一段怎么解？"))
        # 旧代码：history[-10:] 硬上限 + 6000 预算，实测只带入 6 条（3 轮）
        assert len(tags) >= 12, tags
        assert "<A09>" in tags and "<Q05>" in tags, tags

    def test_history_is_contiguous_and_most_recent(self):
        history = _session(15)
        tags = _history_tags(_build_llm_messages(history, CONTEXT, "下一段怎么解？"))
        expected = [m.content[:5] for m in history][-len(tags):]
        assert tags == expected

    def test_message_cap_is_configurable(self, window):
        window(max_input=200_000, max_messages=4)
        tags = _history_tags(_build_llm_messages(_session(15), CONTEXT, "下一段怎么解？"))
        assert tags == ["<Q13>", "<A13>", "<Q14>", "<A14>"]

    def test_token_budget_is_configurable(self, window):
        """总预算调小，历史跟着缩（条数上限给足，确认是预算在起作用）。"""
        window(max_input=16000, max_messages=100)
        wide = _history_tags(_build_llm_messages(_session(15), CONTEXT, "问"))
        window(max_input=8000, max_messages=100)
        narrow = _history_tags(_build_llm_messages(_session(15), CONTEXT, "问"))
        assert 0 < len(narrow) < len(wide)


class TestRollbackReproducesOldWindow:
    def test_6000_10_matches_the_pre_change_numbers(self, window):
        """回滚值 6000/10：与扩窗前同一输入下带入的历史完全相同（旧代码实测为 6 条）。"""
        window(max_input=6000, max_messages=10)
        tags = _history_tags(_build_llm_messages(_session(15), CONTEXT, "下一段怎么解？"))
        assert tags == ["<Q12>", "<A12>", "<Q13>", "<A13>", "<Q14>", "<A14>"]


class TestWiderWindowDoesNotInflateOtherShares:
    """扩窗只给历史。附件钳制与检索截断必须与窗口大小无关。"""

    @staticmethod
    def _final_user(window, max_input: int, **kw) -> str:
        window(max_input=max_input, max_messages=20)
        return _build_llm_messages(**kw)[-1]["content"]

    def test_attachment_clamp_does_not_grow_with_the_window(self, window):
        kw = dict(history=[], context_text="", message="请总结附件", llm_message_override="佛" * 200_000)
        small = self._final_user(window, 6000, **kw)
        big = self._final_user(window, 64000, **kw)
        assert "已截断" in big
        assert len(big) == len(small)

    def test_rag_truncation_does_not_grow_with_the_window(self, window):
        kw = dict(history=[], context_text="藏" * 50_000, message="问")
        small = self._final_user(window, 6000, **kw)
        big = self._final_user(window, 64000, **kw)
        assert len(big) == len(small) < 50_000

    def test_reader_page_question_still_survives(self, window):
        """阅读模式页面原文 10k 字本身就超出基础预算 —— 问题本身不能被饿死。"""
        window(max_input=16000, max_messages=20)
        messages = _build_llm_messages(
            _session(15), "", "请解释这一段的含义",
            reading_context={"title": "妙法蓮華經", "juan_num": 1, "page_content": "頁" * 10000},
        )
        assert "请解释这一段的含义" in messages[-1]["content"]

    def test_total_input_respects_the_configured_budget(self, window):
        """长会话 + 超长附件：整份输入仍在总预算内。"""
        window(max_input=16000, max_messages=20)
        # 不带检索片段：检索包装语（约百字）历来不计入预算，这里只看附件 + 历史
        messages = _build_llm_messages(
            _session(30), "", "请总结附件", llm_message_override="佛" * 200_000,
        )
        total = sum(_estimate_tokens(m["content"]) for m in messages)
        assert total <= 16000
        assert len(messages) > 2  # 历史没被附件挤光
