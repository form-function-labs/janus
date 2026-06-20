from __future__ import annotations

import os
from pathlib import Path

import pytest

from janus.recursion import ENV_GUARD, ReflectionInProgress, ReflectionLock


def test_lock_acquire_and_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "reflecting.lock"
    with ReflectionLock(lock_path):
        assert lock_path.exists()
        assert os.environ.get(ENV_GUARD) == "1"
    assert not lock_path.exists()
    assert ENV_GUARD not in os.environ


def test_env_guard_blocks_reentry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_GUARD, "1")
    with pytest.raises(ReflectionInProgress):  # noqa: SIM117
        with ReflectionLock(tmp_path / "reflecting.lock"):
            pass


def test_stale_lock_is_reclaimed(tmp_path: Path) -> None:
    lock_path = tmp_path / "reflecting.lock"
    lock_path.write_text("999999999", encoding="utf-8")  # an almost-certainly-dead PID
    with ReflectionLock(lock_path):
        assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())
