"""CLI composition-root tests: the JANUS_TIMEOUT env knob (D1 plumbing)."""

from __future__ import annotations

import pytest

from janus import cli

# --- D1: JANUS_TIMEOUT ------------------------------------------------------


def test_load_settings_janus_timeout_defaults_to_600(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JANUS_TIMEOUT", raising=False)
    settings = cli.load_settings()
    assert settings.target_timeout == 600


def test_load_settings_janus_timeout_env_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JANUS_TIMEOUT", "42")
    settings = cli.load_settings()
    assert settings.target_timeout == 42
