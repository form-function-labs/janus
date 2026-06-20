"""Recurrence miner.

Groups sessions into recurring ``RealTask``s by normalized intent. Recurrence is
the abstraction signal: a one-off intent is not worth optimizing the harness
for. A task counts as recurring when its normalized intent appears in at least
``min_count`` distinct sessions of the same project.

Normalization (lowercase, strip punctuation, collapse whitespace) is the
deliberate fix for the reference impl's byte-identity bug, where a one-character
wording change spawned a brand-new task id and broke recurrence detection.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from ..domain.types import RealTask, SessionDigest, Split

_NONWORD = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


def normalize(intent: str) -> str:
    lowered = _NONWORD.sub(" ", intent.lower())
    return _WS.sub(" ", lowered).strip()


def task_id(project: str, normalized: str) -> str:
    digest = hashlib.sha256(f"{project}::{normalized}".encode()).hexdigest()[:12]
    return f"task_{digest}"


class HeuristicMiner:
    def __init__(self, min_count: int = 2) -> None:
        if min_count < 1:
            raise ValueError("min_count must be >= 1")
        self._min_count = min_count

    def mine(self, digests: Sequence[SessionDigest]) -> Sequence[RealTask]:
        groups: dict[str, list[SessionDigest]] = {}
        display: dict[str, str] = {}
        for digest in digests:
            normalized = normalize(digest.intent)
            if not normalized:
                continue
            key = task_id(digest.project, normalized)
            groups.setdefault(key, []).append(digest)
            display.setdefault(key, digest.intent)
        tasks: list[RealTask] = []
        for key, group in groups.items():
            if len(group) < self._min_count:
                continue
            sessions = tuple(d.session_id for d in group)
            tasks.append(RealTask(key, display[key], group[0].project, sessions, Split.TRAIN))
        return tasks
