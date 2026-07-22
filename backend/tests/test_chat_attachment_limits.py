"""Bounds on chat attachments: request count, rate limit, and LLM token cost.

Three related holes, all reachable anonymously:

1. ``attachment_ids`` had no length cap, so a single request could name
   hundreds of ids. Anonymous rows are readable by any anonymous caller
   (by design — see ``services/chat._load_and_render_attachments``), and
   the single-use ``consumed_at`` guard assumed an attacker could only
   probe one sequential id at a time. Batching defeated that assumption.

2. ``/api/chat/attachments`` was not in ``STRICT_PATHS``, so it inherited
   the loose 200/min default on an unauthenticated 10 MB upload that is
   never garbage-collected.

3. ``_build_llm_messages`` sized its token budget from the *original*
   message but sent ``llm_message_override`` (the message with attachment
   text prepended, up to 80k chars each) verbatim, so attachments were
   billed without limit on the platform key.
"""

import pytest
from pydantic import ValidationError

from app.core.rate_limit import STRICT_PATHS
from app.schemas.chat import ChatRequest
from app.services.prompt_builder import _MAX_INPUT_TOKENS, _build_llm_messages, _estimate_tokens

MAX_ATTACHMENTS = 5


class TestAttachmentIdsCap:
    def test_rejects_more_than_the_cap(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="hi", attachment_ids=list(range(1, MAX_ATTACHMENTS + 2)))

    def test_accepts_up_to_the_cap(self):
        req = ChatRequest(message="hi", attachment_ids=list(range(1, MAX_ATTACHMENTS + 1)))
        assert len(req.attachment_ids) == MAX_ATTACHMENTS

    def test_none_still_allowed(self):
        assert ChatRequest(message="hi").attachment_ids is None


class TestUploadRateLimit:
    def test_attachment_upload_has_a_strict_limit(self):
        assert "/api/chat/attachments" in STRICT_PATHS

    def test_limit_is_far_below_the_loose_default(self):
        assert STRICT_PATHS["/api/chat/attachments"] <= 10


class TestOverrideTokenBudget:
    """The override must be clamped, not passed through untrimmed."""

    def test_huge_override_is_truncated(self):
        override = "佛" * 200_000
        messages = _build_llm_messages(
            history=[],
            context_text="",
            message="请总结附件",
            llm_message_override=override,
        )
        final_user = messages[-1]["content"]
        assert _estimate_tokens(final_user) <= _MAX_INPUT_TOKENS

    def test_total_prompt_stays_within_budget(self):
        override = "佛" * 200_000
        messages = _build_llm_messages(
            history=[],
            context_text="",
            message="请总结附件",
            llm_message_override=override,
        )
        total = sum(_estimate_tokens(m["content"]) for m in messages)
        assert total <= _MAX_INPUT_TOKENS

    def test_short_override_is_left_untouched(self):
        override = "【附件】report.txt\n内容摘要"
        messages = _build_llm_messages(
            history=[],
            context_text="",
            message="请总结附件",
            llm_message_override=override,
        )
        assert override in messages[-1]["content"]


class TestUserTurnIsNeverStarved:
    """A large system prompt must not consume the user's own question.

    Reader mode feeds up to 10k chars of page text into the data block, which
    alone exceeds _MAX_INPUT_TOKENS. That drives the residual budget negative,
    and clamping the user turn against a negative budget truncated the actual
    question down to the truncation notice. Before the clamp existed the turn
    was always sent whole, so this would have been a regression: the model
    would receive the page and no question at all.
    """

    def test_reader_mode_keeps_the_question(self):
        messages = _build_llm_messages(
            history=[],
            context_text="",
            message="请解释这一段的含义",
            reading_context={
                "title": "妙法蓮華經",
                "juan_num": 1,
                "page_content": "頁" * 10000,
                "selected_text": "選" * 500,
            },
        )
        assert "请解释这一段的含义" in messages[-1]["content"]

    def test_reader_mode_with_a_master_keeps_the_question(self):
        messages = _build_llm_messages(
            history=[],
            context_text="",
            message="请解释这一段的含义",
            master_id="mahasi-sayadaw",
            reading_context={
                "title": "妙法蓮華經",
                "juan_num": 1,
                "page_content": "頁" * 10000,
                "selected_text": "選" * 500,
            },
        )
        assert "请解释这一段的含义" in messages[-1]["content"]

    def test_attachment_payload_is_still_clamped_in_reader_mode(self):
        """The floor must not become a loophole for the 80k-char attachments."""
        messages = _build_llm_messages(
            history=[],
            context_text="",
            message="请总结附件",
            llm_message_override="佛" * 200_000,
            reading_context={"title": "妙法蓮華經", "juan_num": 1, "page_content": "頁" * 10000},
        )
        assert _estimate_tokens(messages[-1]["content"]) < 20_000
