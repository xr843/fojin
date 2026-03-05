"""Tests for JWT secret validation in production mode."""

import os
import importlib

import pytest


def test_production_rejects_default_secret(monkeypatch):
    """FOJIN_ENV=production with default JWT secret should raise RuntimeError."""
    monkeypatch.setenv("FOJIN_ENV", "production")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        # Force re-import to trigger module-level validation
        import app.config
        importlib.reload(app.config)


def test_production_rejects_short_secret(monkeypatch):
    """FOJIN_ENV=production with short JWT secret should raise RuntimeError."""
    monkeypatch.setenv("FOJIN_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        import app.config
        importlib.reload(app.config)


def test_production_accepts_valid_secret(monkeypatch):
    """FOJIN_ENV=production with a 32+ char secret should not raise."""
    monkeypatch.setenv("FOJIN_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)

    import app.config
    importlib.reload(app.config)
    assert len(app.config.settings.jwt_secret_key) >= 32


def test_development_warns_on_default(monkeypatch):
    """Development mode with default secret should not raise (just warn)."""
    monkeypatch.setenv("FOJIN_ENV", "development")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    import app.config
    importlib.reload(app.config)
    # Should not raise — just log a warning
