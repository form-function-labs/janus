"""CLI composition-root tests: the JANUS_TIMEOUT env knob (D1 plumbing) and
the auth preflight (D2)."""

from __future__ import annotations

from pathlib import Path

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


# --- D2: auth preflight ------------------------------------------------------
#
# Delegates to the real janus.worker.probe_auth (the same probe `doctor` uses)
# rather than a second ad-hoc env check, so there is one diagnostic path for
# "is auth OK" — tests mock `cli.probe_auth`, matching test_doctor.py's style.


def test_run_with_failed_auth_probe_never_builds_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The preflight must fail BEFORE any mining work — proven here by
    asserting build_cycle (the function that wires harvester/miner/worker and
    would start real mining) is never even called."""
    monkeypatch.setenv("JANUS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "probe_auth", lambda claude_path: (False, "not logged in"))
    built: list[bool] = []
    monkeypatch.setattr(cli, "build_cycle", lambda settings: built.append(True))
    with pytest.raises(cli.AuthPreflightError, match="not logged in"):
        cli._dispatch("run")
    assert built == []


def test_dry_run_with_failed_auth_probe_also_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JANUS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "probe_auth", lambda claude_path: (False, "not logged in"))
    with pytest.raises(cli.AuthPreflightError):
        cli._dispatch("dry-run")


def test_run_with_passing_auth_probe_passes_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JANUS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("JANUS_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(cli, "probe_auth", lambda claude_path: (True, ""))
    built: list[bool] = []

    class _StubCycle:
        def run(self, config: object, *, stage: bool) -> object:
            from janus.cycle import SleepReport

            return SleepReport(0, 0, 0, 0, 0, "no-tasks", message="stub")

    def _fake_build_cycle(settings: object) -> _StubCycle:
        built.append(True)
        return _StubCycle()

    monkeypatch.setattr(cli, "build_cycle", _fake_build_cycle)
    rc = cli._dispatch("run")
    assert rc == 0
    assert built == [True]
