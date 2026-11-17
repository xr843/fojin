"""Every AI-chat path opens with the crisis clause (services/safety_clause.py).

Until 2026-11-17 no chat path mentioned self-harm or a hotline at all. These
pin that each path — general, master, reader page, meta question — carries the
clause, at the top of the system prompt, with the referral sentence verbatim.
"""

from app.services.prompt_builder import (
    CITATION_DISCIPLINE_SUFFIX,
    _build_llm_messages,
)
from app.services.safety_clause import (
    CRISIS_CLAUSE,
    MASTER_CRISIS_REMINDER,
    MASTER_SAFETY_CLAUSE,
    REQUIRED_REFERRAL_SENTENCE,
)


def _system(**kwargs) -> str:
    msgs = _build_llm_messages([], "", kwargs.pop("message", "什么是四圣谛？"), **kwargs)
    assert msgs[0]["role"] == "system"
    return msgs[0]["content"]


def test_clause_text_is_the_upstream_one():
    assert REQUIRED_REFERRAL_SENTENCE in CRISIS_CLAUSE
    assert "CRISIS FIRST" in CRISIS_CLAUSE
    assert "不得以念佛、持咒、打坐" in CRISIS_CLAUSE
    # The master version is the whole upstream file: crisis + certification + ranking.
    assert CRISIS_CLAUSE.split("\n\n", 1)[1].strip() in MASTER_SAFETY_CLAUSE
    assert "NO CERTIFICATION" in MASTER_SAFETY_CLAUSE
    assert "NO RANKING BY THE AI" in MASTER_SAFETY_CLAUSE


def test_general_chat_opens_with_crisis_clause_only():
    system = _system()
    assert system.startswith(CRISIS_CLAUSE)
    assert REQUIRED_REFERRAL_SENTENCE in system
    # The other two rules were never evaluated on the general path.
    assert "NO CERTIFICATION" not in system
    # The eval-tuned citation suffix still closes the prompt.
    assert system.rstrip().endswith(CITATION_DISCIPLINE_SUFFIX.strip()) or CITATION_DISCIPLINE_SUFFIX in system


def test_master_mode_opens_with_full_clause_then_persona():
    system = _system(master_id="huineng")
    assert system.startswith(MASTER_SAFETY_CLAUSE)
    assert REQUIRED_REFERRAL_SENTENCE in system
    assert "NO CERTIFICATION" in system and "NO RANKING BY THE AI" in system
    assert "慧能" in system[len(MASTER_SAFETY_CLAUSE):]


def test_reader_page_keeps_clause_on_top():
    system = _system(reading_context={"title": "金剛般若波羅蜜經", "juan_num": 1,
                                      "selected_text": "應無所住而生其心", "page_content": ""})
    assert system.startswith(CRISIS_CLAUSE)
    assert "## 阅读上下文" in system


def test_meta_question_path_has_clause():
    system = _system(message="你是谁？")
    assert system.startswith(CRISIS_CLAUSE)


def test_unknown_master_falls_back_to_general_with_clause():
    system = _system(master_id="nobody")
    assert system.startswith(CRISIS_CLAUSE)


def test_master_mode_restates_the_two_missed_rules_at_the_end():
    """Live probe 2026-11-17: persona voice won over the clause at the top."""
    system = _system(master_id="huineng")
    assert system.rstrip().endswith(MASTER_CRISIS_REMINDER.strip())
    assert REQUIRED_REFERRAL_SENTENCE in MASTER_CRISIS_REMINDER
    assert "不用本祖师口吻" in MASTER_CRISIS_REMINDER


def test_master_reminder_survives_reader_mode():
    system = _system(master_id="huineng", reading_context={"title": "六祖大師法寶壇經", "juan_num": 1,
                                                           "selected_text": "", "page_content": ""})
    assert system.rstrip().endswith(MASTER_CRISIS_REMINDER.strip())


def test_general_chat_has_no_master_reminder():
    assert MASTER_CRISIS_REMINDER.strip() not in _system()
