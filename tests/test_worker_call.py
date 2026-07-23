"""Tests for ``ClaudeCliWorker``'s transport layer: timeout handling (D1).

Fixtures monkeypatch ``subprocess.run`` directly rather than shelling out to a
real ``claude`` binary, so these stay fast and fully offline.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from janus.domain.types import RealTask, Split
from janus.worker.claude_cli import ClaudeCliWorker, WorkerError


def _task(tid: str = "t1") -> RealTask:
    return RealTask(
        id=tid, intent="do the thing", project="p", source_sessions=(), split=Split.TRAIN
    )


# --- D1: a rollout timeout must not abort the run --------------------------


def test_timeout_scores_as_failed_rollout_not_raised() -> None:
    """A subprocess timeout during a rollout must not raise out of .run() — it
    scores as a failed (0.0) rollout, flagged timed_out, so the caller (Cycle)
    can keep going instead of the whole mining pass dying on one slow task."""
    worker = ClaudeCliWorker(role="target", model="haiku", timeout=5)
    with patch(
        "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=5)
    ):
        result = worker.run(_task(), "context")
    assert result.score.value == 0.0
    assert result.timed_out is True


def test_timeout_value_is_forwarded_to_subprocess() -> None:
    """The worker's configured timeout (ultimately the JANUS_TIMEOUT knob) must
    actually reach subprocess.run, not be silently ignored."""
    worker = ClaudeCliWorker(role="target", model="haiku", timeout=42)
    with patch(
        "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=42)
    ) as mock_run:
        worker.run(_task(), "context")
    assert mock_run.call_args.kwargs["timeout"] == 42


def test_non_timeout_workererror_still_raises() -> None:
    """Boundary pin: ONLY TimeoutExpired gets the soft landing. A real failure
    (non-zero exit, not a timeout) must still abort loudly — silently scoring
    it would mask a structural problem (e.g. bad auth) that will fail every
    subsequent rollout too, not just this one."""
    proc = subprocess.CompletedProcess(args=["claude"], returncode=1, stdout="", stderr="boom")
    worker = ClaudeCliWorker(role="target", model="haiku")
    with patch("subprocess.run", return_value=proc), pytest.raises(WorkerError):
        worker.run(_task(), "context")


def test_oserror_still_raises_not_scored() -> None:
    """Boundary pin: an OSError (e.g. claude binary missing) is a launch
    failure, not a timeout — it must still raise, not be swallowed."""
    worker = ClaudeCliWorker(role="target", model="haiku")
    with (
        patch("subprocess.run", side_effect=OSError("claude: command not found")),
        pytest.raises(WorkerError),
    ):
        worker.run(_task(), "context")
