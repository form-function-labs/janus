"""Composite miner — runs several miners and concatenates their tasks.

Lets recurrence and corrections feed the same loop together, behind the single
``RecurrenceMiner`` port the cycle depends on.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.types import RealTask, SessionDigest
from ..ports import RecurrenceMiner


class CompositeMiner:
    def __init__(self, *miners: RecurrenceMiner) -> None:
        self._miners = miners

    def mine(self, digests: Sequence[SessionDigest]) -> Sequence[RealTask]:
        tasks: list[RealTask] = []
        for miner in self._miners:
            tasks.extend(miner.mine(digests))
        return tasks
