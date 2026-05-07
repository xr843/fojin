"""Boundary tests for ``chat._master_scope_text_ids``.

Tests the chat.py boundary helper that translates a MasterProfile into
the scope value retrieve_rag_context expects. The contract this guards
is the three-state asymmetric semantic documented in the helper's
docstring; the bug this defends against is production trace 2026-05-07
msg 4437, where falsy-coalescing collapsed an empty list to None and
silently leaked 楞严经 chunks into the Ajahn Chah master's LLM context.

`test_precise_retrieval` already covers the consumer-side contract
(``scope_text_ids=[]`` blocks every hit). These tests cover the
*producer* side so a future refactor of chat.py that reintroduces
``or None`` fails loudly here, before it reaches the contract test.
"""

from unittest.mock import MagicMock

from app.services.chat import _master_scope_text_ids


def test_no_master_returns_none():
    assert _master_scope_text_ids(None) is None


def test_master_with_empty_text_ids_returns_empty_list_not_none():
    """The exact regression that production msg 4437 exposed. Empty
    list must NOT be coalesced to None — see helper docstring for the
    three-state contract."""
    m = MagicMock()
    m.fojin_text_ids = []
    result = _master_scope_text_ids(m)
    assert result == []
    assert result is not None  # belt and suspenders against future ``or None``


def test_master_with_nonempty_text_ids_returns_list_unchanged():
    m = MagicMock()
    m.fojin_text_ids = [53, 52, 8085, 6513]
    assert _master_scope_text_ids(m) == [53, 52, 8085, 6513]
