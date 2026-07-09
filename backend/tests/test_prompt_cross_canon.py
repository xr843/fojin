"""Locks the cross-canon (跨藏对读) prompt rule 4d.

Rule 4d teaches the LLM to actively use the ``[跨藏对读]`` parallel blocks that
RAG injects (from alignment_pairs and, once #949 lands, MITRA) for cross-canon
comparison — WHILE preserving the anti-fabrication invariant: parallel text has
no ``[出处]`` marker and no clickable original page, so it must never be wrapped
in a ``【《经名》第N卷】`` clickable citation (which rules 4/4b forbid because it
would be a dead link). These asserts guard against a future prompt edit silently
dropping either half.
"""

from app.services.prompt_builder import SYSTEM_PROMPT


def test_prompt_defines_cross_canon_block():
    assert "[跨藏对读]" in SYSTEM_PROMPT
    # It should name the parallel languages so the model recognises the block.
    assert "[梵]" in SYSTEM_PROMPT and "[藏]" in SYSTEM_PROMPT and "[巴利]" in SYSTEM_PROMPT


def test_prompt_encourages_cross_canon_comparison():
    # The activation half: the model is told to use the parallels, not ignore them.
    assert "对照分析" in SYSTEM_PROMPT


def test_prompt_forbids_making_parallels_clickable():
    """Safety half: parallels must NOT become 【《经名》第N卷】 dead links."""
    assert "死链" in SYSTEM_PROMPT
    # Rule 4d explicitly cross-references the anti-fake-citation rules.
    assert "违反规则 4/4b" in SYSTEM_PROMPT


def test_prompt_rule_4d_sits_between_4c_and_rule_5():
    """Ordering sanity: 4d is grouped with the other citation rules (4/4a/4b/4c),
    not appended somewhere unrelated."""
    i_4c = SYSTEM_PROMPT.find("4c.")
    i_4d = SYSTEM_PROMPT.find("4d.")
    i_5 = SYSTEM_PROMPT.find("5. 如果通识")
    assert -1 < i_4c < i_4d < i_5


def test_prompt_preserves_existing_verbatim_rule():
    """4d must not have clobbered the pre-existing 4c verbatim-quote constraint."""
    assert "4c." in SYSTEM_PROMPT
    assert "逐字来自检索片段" in SYSTEM_PROMPT
