"""Durable noise-pattern store — persists JANUS_IGNORE_PATTERNS to disk.

Patterns are stored one-per-line in ``$JANUS_HOME/ignore-patterns``. The file
is human-readable and ``grep``-able. Blank lines and whitespace-only lines are
silently skipped on read. The store deduplicates on write (first-seen order is
preserved).
"""

from __future__ import annotations

from pathlib import Path


class IgnorePatternStore:
    """Filesystem adapter over ``$JANUS_HOME/ignore-patterns``."""

    __slots__ = ("_path",)

    def __init__(self, home: Path) -> None:
        self._path = home / "ignore-patterns"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def list(self) -> tuple[str, ...]:
        """Return all stored patterns, blank lines excluded."""
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return ()
        return tuple(line for line in text.splitlines() if line.strip())

    def add(self, pattern: str) -> None:
        """Append *pattern* unless already present; creates the file (and parent dir) if needed."""
        existing = self.list()
        if pattern in existing:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(pattern + "\n")

    def remove(self, pattern: str) -> None:
        """Remove *pattern* from the store; no-op if absent or file missing."""
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return
        lines = [line for line in text.splitlines() if line.strip() and line != pattern]
        self._path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
