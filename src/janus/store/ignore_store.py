"""Durable noise-pattern store — persists JANUS_IGNORE_PATTERNS to disk.

Patterns are stored one-per-line in ``$JANUS_HOME/ignore-patterns``. The file
is human-readable and ``grep``-able. Blank lines and whitespace-only lines are
silently skipped on read. The store deduplicates on write (first-seen order is
preserved).

Every mutation funnels through :meth:`IgnorePatternStore._write`, which rewrites
the whole file atomically (temp-file + ``os.replace``, the same discipline as
:class:`~janus.store.adopter.FileAdopter`). Routing both ``add`` and ``remove``
through one canonical writer guarantees the on-disk form is always normalized —
one pattern per line, trailing newline — so a hand-edited file that lacks a
trailing newline can never fuse two patterns into one.
"""

from __future__ import annotations

import os
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
        """Return all stored patterns, blank lines excluded.

        Only a *missing* file degrades to an empty store; permission errors,
        path-type conflicts, and other real I/O failures propagate so a broken
        store surfaces loudly instead of masquerading as "no patterns".
        """
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        return tuple(line for line in text.splitlines() if line.strip())

    def add(self, pattern: str) -> None:
        """Persist *pattern* unless already present; creates file + parent dir as needed.

        Raises :class:`ValueError` for a blank/whitespace-only pattern (it would be
        filtered back out on read) or one containing a newline (it would be split
        into separate entries that ``remove`` could never match as the original).
        """
        pattern = self._validate(pattern)
        existing = self.list()
        if pattern in existing:
            return
        self._write((*existing, pattern))

    def remove(self, pattern: str) -> None:
        """Remove *pattern* from the store; no-op if absent or file missing."""
        existing = self.list()
        if pattern not in existing:
            return
        self._write(tuple(p for p in existing if p != pattern))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(pattern: str) -> str:
        if not pattern.strip():
            raise ValueError("ignore pattern must be non-empty")
        if "\n" in pattern or "\r" in pattern:
            raise ValueError("ignore pattern must be a single line")
        return pattern

    def _write(self, patterns: tuple[str, ...]) -> None:
        """Atomically rewrite the store from *patterns* (one per line, canonical).

        Deduplicates (first-seen order preserved) so every mutation re-normalizes
        the file — honouring the "deduplicates on write" contract even when the
        file was hand-edited to contain repeats.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(p + "\n" for p in dict.fromkeys(patterns))
        tmp = self._path.parent / f".{self._path.name}.janus.tmp"
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, self._path)  # atomic swap
