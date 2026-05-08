"""KDF v1/v2 round-trip and cross-version contract tests.

Covers app.core.crypto + the boot-time validation in app.config.  We do
NOT exercise the production fail-fast path here (that runs once at
import time and is covered by a manual smoke test); the focus is the
runtime API surface that callers actually touch.
"""

import base64
import hashlib
import importlib
import os

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.core import crypto as crypto_module
from app.core.crypto import (
    KDF_VERSION_V1,
    KDF_VERSION_V2,
    decrypt_api_key,
    encrypt_api_key,
)


@pytest.fixture
def fixed_v2_key(monkeypatch):
    """Pin a deterministic v2 key for the duration of a test."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "api_key_encryption_key", key)
    return key


def test_v2_round_trip(fixed_v2_key):
    cipher, version = encrypt_api_key("sk-secret-xyz")
    assert version == KDF_VERSION_V2
    assert decrypt_api_key(cipher, version) == "sk-secret-xyz"


def test_v1_round_trip_via_legacy_path(monkeypatch):
    """v1 ciphertext (sealed with the SHA-256(JWT_SECRET) KDF) decrypts."""
    monkeypatch.setattr(settings, "jwt_secret_key", "test-jwt-secret-32-chars-long-xx")
    legacy_key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.jwt_secret_key.encode()).digest()
    )
    legacy_cipher = Fernet(legacy_key).encrypt(b"sk-legacy").decode()

    assert decrypt_api_key(legacy_cipher, KDF_VERSION_V1) == "sk-legacy"


def test_v2_blob_does_not_decrypt_under_v1_key(fixed_v2_key, monkeypatch):
    """A v2 ciphertext is not recoverable with the legacy v1 KDF alone.

    We assert this by reaching past ``decrypt_api_key`` (which has a
    cross-version fallback) directly into ``_get_v1_fernet`` so the test
    is meaningful.
    """
    monkeypatch.setattr(settings, "jwt_secret_key", "test-jwt-secret-32-chars-long-xx")
    cipher, _ = encrypt_api_key("sk-v2-only")
    with pytest.raises(InvalidToken):
        crypto_module._get_v1_fernet().decrypt(cipher.encode())


def test_decrypt_dispatches_by_requested_version(fixed_v2_key, monkeypatch):
    """If caller wrongly tags a v2 blob as v1, the fallback recovers it.

    This is the migration-window safety net: a row whose
    ``api_key_kdf_version`` is still 1 but whose ciphertext is already
    v2 (e.g. a save that landed between the column add and the script
    run) must still decrypt.
    """
    monkeypatch.setattr(settings, "jwt_secret_key", "test-jwt-secret-32-chars-long-xx")
    cipher, _ = encrypt_api_key("sk-mismatched-tag")

    assert decrypt_api_key(cipher, KDF_VERSION_V1) == "sk-mismatched-tag"


def test_unknown_version_raises():
    with pytest.raises(ValueError, match="Unknown KDF version"):
        decrypt_api_key("ignored", version=99)


def test_dev_mode_generates_ephemeral_key(monkeypatch):
    """When API_KEY_ENCRYPTION_KEY is unset in dev, config bootstraps one."""
    monkeypatch.setenv("FOJIN_ENV", "development")
    monkeypatch.delenv("API_KEY_ENCRYPTION_KEY", raising=False)
    # Reload the config module so the boot-time block runs again under
    # the patched env. ``importlib.reload`` re-executes the module body.
    import app.config as cfg

    importlib.reload(cfg)
    assert cfg.settings.api_key_encryption_key  # generated, non-empty
    # And it round-trips through Fernet:
    Fernet(cfg.settings.api_key_encryption_key.encode())


def test_production_missing_key_fails_fast(monkeypatch):
    """Empty API_KEY_ENCRYPTION_KEY in prod must raise at import time."""
    monkeypatch.setenv("FOJIN_ENV", "production")
    monkeypatch.setenv(
        "JWT_SECRET_KEY", "x" * 40
    )  # satisfy the JWT fail-fast so we hit our branch
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", "")

    import app.config as cfg

    with pytest.raises(RuntimeError, match="API_KEY_ENCRYPTION_KEY"):
        importlib.reload(cfg)

    # Restore module to a sane state for sibling tests in this process.
    monkeypatch.setenv("FOJIN_ENV", "development")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    importlib.reload(cfg)


def test_production_invalid_key_fails_fast(monkeypatch):
    monkeypatch.setenv("FOJIN_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", "not-a-fernet-key")

    import app.config as cfg

    with pytest.raises(RuntimeError, match="not a valid Fernet key"):
        importlib.reload(cfg)

    monkeypatch.setenv("FOJIN_ENV", "development")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    importlib.reload(cfg)


# Sanity: the os import isn't actually used inside test bodies above —
# keep the linter happy without dropping it (importing config indirectly
# can pull in env reads that future tests will want to reach for).
_ = os.environ
