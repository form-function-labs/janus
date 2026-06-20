"""Anti-recursion lock — env fast-path + filesystem PID backstop.

The reference impl prevented a review worker from re-triggering itself with a
single environment sentinel. That's the cheap common case, but an env var is
soft: anything that crosses a process boundary without forwarding it disarms the
guard. So Janus models the loop as a typestate — ``Idle -> Reflecting -> Idle`` —
where ``Reflecting`` is *witnessed by a PID lockfile*. Recursion becomes
unrepresentable even if the env var is lost, and a stale lock (dead PID) is
reclaimed rather than wedging the loop forever.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from types import TracebackType

ENV_GUARD = "JANUS_REVIEWING"


class ReflectionInProgress(RuntimeError):
    """A reflection cycle is already running — refuse to start a second."""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    except OSError:
        return False
    return True


class ReflectionLock:
    """Context manager enforcing single-flight reflection."""

    def __init__(self, lock_path: Path) -> None:
        self._path = lock_path

    def __enter__(self) -> ReflectionLock:
        if os.environ.get(ENV_GUARD):
            raise ReflectionInProgress("env guard set: already inside a reflection cycle")
        if self._path.exists():
            pid = self._read_pid()
            if pid is not None and _pid_alive(pid):
                raise ReflectionInProgress(f"lock held by live pid {pid}")
            # Stale lock (dead or unreadable PID): reclaim it.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(str(os.getpid()), encoding="utf-8")
        os.environ[ENV_GUARD] = "1"
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        os.environ.pop(ENV_GUARD, None)
        with contextlib.suppress(OSError):
            self._path.unlink()

    def _read_pid(self) -> int | None:
        try:
            return int(self._path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
