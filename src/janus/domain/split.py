"""The split policy — deterministic, seeded, dream-excluding.

Val/test assignment is a stable hash of the task id, so the same task always
lands in the same bucket across nights (no ``random``, no ``shuffle``). Dreams
never reach this function: they are ``DreamTask``, which has no split to assign.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .types import RealTask, Split


@dataclass(frozen=True, slots=True)
class SplitConfig:
    seed: int = 42
    val_fraction: float = 0.34
    test_fraction: float = 0.0

    def __post_init__(self) -> None:
        if self.val_fraction < 0 or self.test_fraction < 0:
            raise ValueError("fractions must be >= 0")
        if self.val_fraction + self.test_fraction > 1.0:
            raise ValueError("val + test fraction must be <= 1.0")


def _bucket(seed: int, task_id: str) -> int:
    digest = hashlib.sha256(f"{seed}:{task_id}".encode()).hexdigest()
    return int(digest, 16) % 100


def assign_splits(
    tasks: Sequence[RealTask], config: SplitConfig | None = None
) -> tuple[RealTask, ...]:
    """Return new RealTasks with a stable, seeded split assigned. Pure."""
    cfg = config or SplitConfig()
    val_cut = round(cfg.val_fraction * 100)
    test_cut = val_cut + round(cfg.test_fraction * 100)
    out: list[RealTask] = []
    for task in tasks:
        bucket = _bucket(cfg.seed, task.id)
        if bucket < val_cut:
            split = Split.VAL
        elif bucket < test_cut:
            split = Split.TEST
        else:
            split = Split.TRAIN
        out.append(replace(task, split=split))
    return tuple(out)
