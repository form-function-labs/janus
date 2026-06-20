from __future__ import annotations

from collections import Counter

import pytest

from janus.domain.split import SplitConfig, assign_splits
from janus.domain.types import DreamTask, RealTask, Split


def _tasks(n: int) -> tuple[RealTask, ...]:
    return tuple(RealTask(f"id{i}", f"intent {i}", "proj", (), Split.TRAIN) for i in range(n))


def test_assignment_is_deterministic() -> None:
    tasks = _tasks(50)
    assert [t.split for t in assign_splits(tasks)] == [t.split for t in assign_splits(tasks)]


def test_distribution_roughly_matches_fraction() -> None:
    counts = Counter(t.split for t in assign_splits(_tasks(200), SplitConfig(val_fraction=0.34)))
    assert 0.25 <= counts[Split.VAL] / 200 <= 0.43
    assert counts[Split.TEST] == 0


def test_test_split_supported() -> None:
    counts = Counter(
        t.split
        for t in assign_splits(_tasks(200), SplitConfig(val_fraction=0.2, test_fraction=0.2))
    )
    assert counts[Split.VAL] > 0
    assert counts[Split.TEST] > 0


def test_dream_task_structurally_has_no_split() -> None:
    # The invariant as a type: a dream cannot carry a val/test split.
    dream = DreamTask("d1", "intent", seed_id="id0")
    assert not hasattr(dream, "split")


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        SplitConfig(val_fraction=0.7, test_fraction=0.5)
