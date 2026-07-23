"""CLI composition-root tests: the JANUS_TIMEOUT env knob (D1 plumbing), the
auth preflight (D2), and the stale-staging warning (D3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from janus import cli
from janus.clock import SystemClock
from janus.domain.gate import gate
from janus.domain.proposal import Proposal
from janus.domain.types import Edit, EditOp, PairedOutcome, Score, Surface
from janus.store.proposal_store import FileProposalStore

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


# --- D3: stale staging -------------------------------------------------------


def _staged_proposal(target: Path, created: str) -> Proposal:
    outcome = gate([PairedOutcome("t", Score(0.0), Score(1.0))])
    return Proposal(
        surface=Surface.MEMORY,
        target_name=target.name,
        target_path=str(target),
        baseline_text="old",
        candidate_text="new",
        edits=(Edit(EditOp.ADD, Surface.MEMORY, "a rule"),),
        outcome=outcome,
        created=created,
    )


def test_stale_staging_warns_when_older_than_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JANUS_HOME", str(tmp_path / "home"))
    home = tmp_path / "home"
    store = FileProposalStore(home, SystemClock())
    old = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    store.stage(_staged_proposal(tmp_path / "MEMORY.md", old))

    settings = cli.load_settings()
    cli._check_stale_staging(settings)
    out = capsys.readouterr().out
    assert "10d" in out
    assert str(tmp_path / "MEMORY.md") in out


def test_fresh_staging_does_not_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JANUS_HOME", str(tmp_path / "home"))
    home = tmp_path / "home"
    store = FileProposalStore(home, SystemClock())
    fresh = datetime.now(UTC).isoformat()
    store.stage(_staged_proposal(tmp_path / "MEMORY.md", fresh))

    settings = cli.load_settings()
    cli._check_stale_staging(settings)
    assert capsys.readouterr().out == ""


def test_no_staging_does_not_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JANUS_HOME", str(tmp_path / "home"))
    settings = cli.load_settings()
    cli._check_stale_staging(settings)
    assert capsys.readouterr().out == ""


def test_stale_staging_threshold_is_env_configurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JANUS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("JANUS_STALE_STAGING_DAYS", "3")
    home = tmp_path / "home"
    store = FileProposalStore(home, SystemClock())
    five_days = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    store.stage(_staged_proposal(tmp_path / "MEMORY.md", five_days))

    settings = cli.load_settings()
    cli._check_stale_staging(settings)
    out = capsys.readouterr().out
    assert "5d" in out  # would NOT warn at the default 7d threshold
