"""Runtime contract tests for ADK coach startup safety."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "garmin_coach" / "src"))
sys.path.insert(1, str(REPO_ROOT / "src"))

from coach_adk.runtime import AdkCoachRuntime  # noqa: E402


def _config(env: str = "development") -> SimpleNamespace:
    return SimpleNamespace(
        google_cloud=SimpleNamespace(api_key="fake-key"),
        features=SimpleNamespace(enable_nl2sql=False, enable_charts=False),
        app=SimpleNamespace(env=env),
    )


def test_runtime_fails_on_invalid_async_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADK_SESSION_DB_URL", "sqlite:///tmp/bad.db")
    monkeypatch.setenv("ADK_SESSION_STRICT_STARTUP", "false")
    with pytest.raises(RuntimeError, match="Invalid ADK_SESSION_DB_URL async driver"):
        AdkCoachRuntime(config=_config())


def test_runtime_requires_session_db_url_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ADK_SESSION_DB_URL", raising=False)
    with pytest.raises(RuntimeError, match="ADK_SESSION_DB_URL is required outside"):
        AdkCoachRuntime(config=_config(env="production"))
