"""Tests for the curated LLM catalog and the per-message model override.

Guards two contracts:

1. ``CATALOG`` ids are stable and unique — frontend localStorage relies on
   these strings.
2. ``_resolve_with_model_override`` selects the right (url, key, model)
   triple based on BYOK vs platform availability, and falls back gracefully
   on unknown ids so a stale localStorage value never breaks chat.
"""

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ServiceError
from app.services import chat as chat_module
from app.services.chat import (
    PROVIDER_URLS,
    _resolve_llm_config,
    _resolve_with_model_override,
)
from app.services.llm_catalog import CATALOG, CATALOG_BY_ID, DEFAULT_MODEL_ID


def test_catalog_ids_are_unique():
    ids = [opt.id for opt in CATALOG]
    assert len(ids) == len(set(ids)), "Duplicate ids in CATALOG"


def test_catalog_by_id_matches_catalog():
    assert set(CATALOG_BY_ID.keys()) == {opt.id for opt in CATALOG}


def test_default_model_id_is_in_catalog():
    assert DEFAULT_MODEL_ID in CATALOG_BY_ID


def test_resolve_with_no_model_id_falls_back_to_default(monkeypatch):
    """No model_id → behave exactly like _resolve_llm_config(user)."""
    monkeypatch.setattr(chat_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(chat_module.settings, "llm_api_key", "platform-key")
    monkeypatch.setattr(chat_module.settings, "llm_model", "deepseek-v4-pro")

    assert _resolve_with_model_override(None, None) == _resolve_llm_config(None)


def test_resolve_with_unknown_model_id_falls_back_gracefully(monkeypatch):
    """Stale localStorage id must not 400 — fall back to default."""
    monkeypatch.setattr(chat_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(chat_module.settings, "llm_api_key", "platform-key")
    monkeypatch.setattr(chat_module.settings, "llm_model", "deepseek-v4-pro")

    result = _resolve_with_model_override(None, "vendor:nonsense-model")
    assert result == _resolve_llm_config(None)


def test_resolve_platform_deepseek_pro(monkeypatch):
    """DeepSeek V4 Pro on platform key → returns deepseek URL + override model."""
    monkeypatch.setattr(chat_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(chat_module.settings, "llm_api_key", "platform-key")

    url, key, model, is_byok, provider = _resolve_with_model_override(None, "deepseek:v4-pro")
    assert url == PROVIDER_URLS["deepseek"]
    assert key == "platform-key"
    assert model == "deepseek-v4-pro"
    assert is_byok is False
    assert provider == "deepseek"


def test_resolve_platform_mismatch_raises(monkeypatch):
    """Platform configured as DeepSeek, user picks Moonshot, no BYOK → ServiceError."""
    monkeypatch.setattr(chat_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(chat_module.settings, "llm_api_key", "platform-key")

    with pytest.raises(ServiceError) as exc_info:
        _resolve_with_model_override(None, "moonshot:kimi-k2.6")
    # User-facing message must mention the provider so user knows which key to add
    assert "moonshot" in str(exc_info.value).lower() or "Kimi" in str(exc_info.value)


def test_resolve_byok_matching_provider_overrides_model(monkeypatch):
    """User has Moonshot BYOK, picks Moonshot model → use BYOK key + override model."""
    monkeypatch.setattr(chat_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(chat_module.settings, "llm_api_key", "platform-key")
    monkeypatch.setattr(
        chat_module, "decrypt_api_key", lambda blob, version=1: "user-moonshot-key"
    )

    user = MagicMock()
    user.id = 42
    user.encrypted_api_key = b"encrypted-blob"
    user.api_provider = "moonshot"
    user.api_model = "kimi-something-stale"

    url, key, model, is_byok, provider = _resolve_with_model_override(
        user, "moonshot:kimi-k2.6"
    )
    assert url == PROVIDER_URLS["moonshot"]
    assert key == "user-moonshot-key"
    assert model == "kimi-k2.6"
    assert is_byok is True
    assert provider == "moonshot"


def test_resolve_byok_provider_mismatch_falls_to_platform(monkeypatch):
    """User has Moonshot BYOK but picks DeepSeek → platform path (DeepSeek configured)."""
    monkeypatch.setattr(chat_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(chat_module.settings, "llm_api_key", "platform-key")

    user = MagicMock()
    user.id = 42
    user.encrypted_api_key = b"encrypted-blob"
    user.api_provider = "moonshot"

    url, key, model, is_byok, provider = _resolve_with_model_override(
        user, "deepseek:v4-pro"
    )
    assert url == PROVIDER_URLS["deepseek"]
    assert key == "platform-key"
    assert model == "deepseek-v4-pro"
    assert is_byok is False
    assert provider == "deepseek"
