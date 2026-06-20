"""Ports — the ``Protocol`` interfaces the orchestrator depends on.

Adapters in ``harvest/``, ``mine/``, ``worker/``, and ``store/`` implement these.
The domain core never imports an adapter; the orchestrator (``cycle.py``) is
handed concrete adapters and talks to them only through these shapes. That's the
hexagon: swap the real ``claude -p`` worker for a recorded one, or the file
store for an in-memory one, without the domain noticing.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .domain.proposal import AdoptResult, Proposal
from .domain.types import Edit, RealTask, RolloutResult, SessionDigest, Surface, Task


class TranscriptHarvester(Protocol):
    def harvest(self, since: float | None = None) -> Sequence[SessionDigest]: ...


class RecurrenceMiner(Protocol):
    def mine(self, digests: Sequence[SessionDigest]) -> Sequence[RealTask]: ...


class TargetWorker(Protocol):
    """Executes a task under a given context (the text-state). The frozen model."""

    def run(self, task: Task, context: str) -> RolloutResult: ...


class OptimizerWorker(Protocol):
    """Proposes bounded edits from scored rollouts.

    The (ideally stronger) optimizer. It never grades the run it produced —
    optimizer ≠ target is enforced by wiring two distinct instances.
    """

    def reflect(self, state_text: str, results: Sequence[RolloutResult]) -> Sequence[Edit]: ...


class TextState(Protocol):
    """A bounded markdown text-state (memory / skill / CLAUDE.md)."""

    name: str
    surface: Surface

    def read(self) -> str: ...

    def render(self, edits: Sequence[Edit]) -> str: ...


class ProposalStore(Protocol):
    def stage(self, proposal: Proposal) -> str: ...

    def latest(self) -> Proposal | None: ...


class Adopter(Protocol):
    def adopt(self, proposal: Proposal) -> AdoptResult: ...


class Clock(Protocol):
    def now_iso(self) -> str: ...

    def monotonic(self) -> float: ...
