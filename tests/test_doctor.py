"""Tests for doctor preflight (FOR-569) — red before green.

Boundary inventory:
  - binary not on PATH → ✗ binary check, hint about install
  - binary on PATH → ✓ binary check
  - JANUS_HOME not writable (chmod 555) → ✗ home check, hint about permissions
  - JANUS_HOME dir missing → doctor creates it → ✓ home check
  - probe_fn returns (False, ...) → ✗ auth check, hint about login
  - probe_fn returns (True, "") → ✓ auth check
  - all three pass → _dispatch("doctor") returns 0, prints ✓ for each
  - binary missing alone → _dispatch returns non-zero
  - probe fail alone → _dispatch returns non-zero
  - home not writable alone → _dispatch returns non-zero

DI seam: _doctor_checks(settings, probe_fn) — probe_fn is injectable so CI
never spawns a real model call. _dispatch("doctor") wires in the real probe_auth
from the worker adapter; tests supply a lambda or a named stub.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from janus.cli import DoctorCheck, Settings, _dispatch, _doctor_checks
from janus.domain.types import Surface

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(tmp_path: Path, *, claude_path: str = "claude") -> Settings:
    """Minimal valid Settings for doctor tests."""
    return Settings(
        home=tmp_path / "janus-home",
        projects_dir=tmp_path / "projects",
        target_path=tmp_path / "MEMORY.md",
        optimizer_model="sonnet",
        target_model="haiku",
        claude_path=claude_path,
        min_recurrence=2,
        val_fraction=0.34,
        seed=42,
        min_net=1,
        regression_budget=0,
        surface=Surface.MEMORY,
    )


def _probe_ok(claude_path: str) -> tuple[bool, str]:
    return (True, "")


def _probe_fail(claude_path: str) -> tuple[bool, str]:
    return (False, "auth probe failed: exit 1")


def _binary_check(checks: list[DoctorCheck]) -> DoctorCheck:
    return next(c for c in checks if "binary" in c.label or "claude" in c.label.lower())


def _home_check(checks: list[DoctorCheck]) -> DoctorCheck:
    return next(c for c in checks if "home" in c.label.lower())


def _auth_check(checks: list[DoctorCheck]) -> DoctorCheck:
    return next(c for c in checks if "auth" in c.label.lower())


# ---------------------------------------------------------------------------
# _doctor_checks unit — binary check
# ---------------------------------------------------------------------------


def test_binary_missing_yields_failing_check(tmp_path: Path) -> None:
    """When claude binary is not on PATH, the binary check must be ✗ with a hint."""
    settings = _make_settings(tmp_path, claude_path="claude-not-found-xyz-abc")
    checks = _doctor_checks(settings, _probe_ok)
    chk = _binary_check(checks)
    assert not chk.ok
    assert chk.hint  # fix hint must be non-empty


def test_binary_present_yields_passing_check(tmp_path: Path) -> None:
    """When claude binary resolves on PATH, the binary check must be ✓."""
    settings = _make_settings(tmp_path)
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        checks = _doctor_checks(settings, _probe_ok)
    chk = _binary_check(checks)
    assert chk.ok
    assert chk.hint == ""  # no hint needed when passing


# ---------------------------------------------------------------------------
# _doctor_checks unit — home writability check
# ---------------------------------------------------------------------------


def test_home_not_writable_yields_failing_check(tmp_path: Path) -> None:
    """A chmod-555 JANUS_HOME must make the home check ✗."""
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    settings = Settings(
        home=locked,
        projects_dir=tmp_path / "projects",
        target_path=tmp_path / "MEMORY.md",
        optimizer_model="sonnet",
        target_model="haiku",
        claude_path="claude",
        min_recurrence=2,
        val_fraction=0.34,
        seed=42,
        min_net=1,
        regression_budget=0,
    )
    try:
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            checks = _doctor_checks(settings, _probe_ok)
        chk = _home_check(checks)
        assert not chk.ok
        assert chk.hint  # must carry fix hint referencing the path
    finally:
        locked.chmod(0o755)  # restore so pytest cleanup can remove it


def test_home_missing_dir_creates_and_passes(tmp_path: Path) -> None:
    """When JANUS_HOME does not exist, doctor must create it and return ✓."""
    missing = tmp_path / "brand-new-home"
    assert not missing.exists()
    settings = Settings(
        home=missing,
        projects_dir=tmp_path / "projects",
        target_path=tmp_path / "MEMORY.md",
        optimizer_model="sonnet",
        target_model="haiku",
        claude_path="claude",
        min_recurrence=2,
        val_fraction=0.34,
        seed=42,
        min_net=1,
        regression_budget=0,
    )
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        checks = _doctor_checks(settings, _probe_ok)
    chk = _home_check(checks)
    assert chk.ok
    assert missing.is_dir()  # side-effect: directory was created


# ---------------------------------------------------------------------------
# _doctor_checks unit — auth probe check
# ---------------------------------------------------------------------------


def test_probe_failure_yields_failing_auth_check(tmp_path: Path) -> None:
    """An injected failing probe must make the auth check ✗ with a hint."""
    settings = _make_settings(tmp_path)
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        checks = _doctor_checks(settings, _probe_fail)
    chk = _auth_check(checks)
    assert not chk.ok
    assert chk.hint  # fix hint must be non-empty


def test_probe_success_yields_passing_auth_check(tmp_path: Path) -> None:
    """An injected passing probe must make the auth check ✓."""
    settings = _make_settings(tmp_path)
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        checks = _doctor_checks(settings, _probe_ok)
    chk = _auth_check(checks)
    assert chk.ok
    assert chk.hint == ""


# ---------------------------------------------------------------------------
# _doctor_checks returns exactly three checks in a stable order
# ---------------------------------------------------------------------------


def test_returns_three_checks_in_order(tmp_path: Path) -> None:
    """doctor must always emit binary / home / auth checks (in that order)."""
    settings = _make_settings(tmp_path)
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        checks = _doctor_checks(settings, _probe_ok)
    assert len(checks) == 3
    labels = [c.label for c in checks]
    # binary first, home second, auth third
    assert any("binary" in lbl or "claude" in lbl.lower() for lbl in labels[:1])
    assert any("home" in lbl.lower() for lbl in labels[1:2])
    assert any("auth" in lbl.lower() for lbl in labels[2:3])


# ---------------------------------------------------------------------------
# _dispatch("doctor") integration — exit codes
# ---------------------------------------------------------------------------


def test_dispatch_doctor_all_pass_returns_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """All checks passing → exit code 0, output contains ✓ markers."""
    os.environ["JANUS_HOME"] = str(tmp_path / "home")
    try:
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("janus.cli.probe_auth", return_value=(True, "")),
        ):
            rc = _dispatch("doctor")
        assert rc == 0
        out = capsys.readouterr().out
        assert "✓" in out
    finally:
        os.environ.pop("JANUS_HOME", None)


def test_dispatch_doctor_binary_missing_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Binary not on PATH → exit code non-zero, output contains ✗."""
    os.environ["JANUS_HOME"] = str(tmp_path)
    os.environ["JANUS_CLAUDE_PATH"] = "claude-not-found-xyz-abc"
    try:
        # probe_auth is still patched to avoid subprocess; binary check should fail first
        with patch("janus.cli.probe_auth", return_value=(False, "binary missing")):
            rc = _dispatch("doctor")
        assert rc != 0
        out = capsys.readouterr().out
        assert "✗" in out
    finally:
        os.environ.pop("JANUS_HOME", None)
        os.environ.pop("JANUS_CLAUDE_PATH", None)


def test_dispatch_doctor_probe_fail_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Auth probe failing → exit code non-zero even if binary and home pass."""
    os.environ["JANUS_HOME"] = str(tmp_path / "home3")
    try:
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("janus.cli.probe_auth", return_value=(False, "not logged in")),
        ):
            rc = _dispatch("doctor")
        assert rc != 0
        out = capsys.readouterr().out
        assert "✗" in out
    finally:
        os.environ.pop("JANUS_HOME", None)


def test_dispatch_doctor_home_not_writable_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Home not writable → exit code non-zero."""
    locked = tmp_path / "locked2"
    locked.mkdir()
    locked.chmod(0o555)
    os.environ["JANUS_HOME"] = str(locked)
    try:
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("janus.cli.probe_auth", return_value=(True, "")),
        ):
            rc = _dispatch("doctor")
        assert rc != 0
    finally:
        locked.chmod(0o755)
        os.environ.pop("JANUS_HOME", None)
