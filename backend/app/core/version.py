"""Runtime deploy identity helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_NAME = "fojin"
DEFAULT_APP_VERSION = "3.0.0"
DEPLOY_VERSION_FILE = Path(__file__).resolve().parents[2] / ".deploy-version.json"


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _read_deploy_version_file() -> dict[str, Any]:
    try:
        data = json.loads(DEPLOY_VERSION_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def get_deploy_identity() -> dict[str, str]:
    """Return app/version/commit identity for deploy smoke checks."""

    file_data = _read_deploy_version_file()
    commit = (
        _clean(os.environ.get("FOJIN_COMMIT_SHA"))
        or _clean(os.environ.get("GITHUB_SHA"))
        or _clean(str(file_data.get("commit") or ""))
        or "unknown"
    )
    version = (
        _clean(os.environ.get("APP_VERSION"))
        or _clean(str(file_data.get("version") or ""))
        or DEFAULT_APP_VERSION
    )
    commit_short = commit[:7] if commit != "unknown" else "unknown"
    return {
        "app": APP_NAME,
        "version": version,
        "commit": commit,
        "commit_short": commit_short,
    }
