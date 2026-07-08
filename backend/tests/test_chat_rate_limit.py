"""The chat (AI Q&A) endpoints must be strict-rate-limited.

Chat is the most expensive endpoint: RAG retrieval always spends the platform
embedding key (even for BYOK users), then a long streaming LLM call holds a DB
pool slot. It was previously left at the loose per-IP default (200/min) while
cheaper paid-inference endpoints (semantic search, research, ai-diff) were
capped. These tests lock chat into STRICT_PATHS at its configured, far-lower
limit so a future refactor can't silently drop the protection.
"""

from app.config import settings
from app.core.rate_limit import STRICT_PATHS


def test_chat_endpoints_are_strict_rate_limited():
    """Both the sync twin and the streaming path must be strict-limited."""
    assert "/api/chat" in STRICT_PATHS
    assert "/api/chat/stream" in STRICT_PATHS


def test_chat_limit_uses_configured_value():
    assert STRICT_PATHS["/api/chat"] == settings.rate_limit_chat
    assert STRICT_PATHS["/api/chat/stream"] == settings.rate_limit_chat


def test_chat_limit_is_far_below_the_default():
    """The whole point is to cap the expensive endpoint well under the loose
    per-IP default — otherwise adding it to STRICT_PATHS buys nothing."""
    assert settings.rate_limit_chat < settings.rate_limit_default
