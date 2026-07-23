"""Cycle-level test for D1's "run completes" half of the AC.

test_worker_call.py proves ClaudeCliWorker.run() converts a subprocess timeout
into a scored-failure RolloutResult instead of raising. This file proves the
other half: once Cycle receives that RolloutResult, it aggregates the timeout
count and surfaces it in SleepReport (fail-loud) instead of letting it vanish
into an indistinguishable 0.0 score.

Fakes are hand-rolled (no test_cycle.py existed before this — Cycle previously
had only a live/skip e2e test) rather than reused, since the Protocol ports
are small and a mocking framework would obscure more than it saves here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from janus.clock import SystemClock
from janus.cycle import Cycle, CycleConfig
from janus.domain.gate import GatePolicy
from janus.domain.split import SplitConfig
from janus.domain.types import (
    Edit,
    EditOp,
    RealTask,
    RolloutResult,
    Score,
    SessionDigest,
    Split,
    Surface,
    Task,
)
from janus.recursion import ReflectionLock
from janus.store.proposal_store import FileProposalStore

# Stable under SplitConfig(seed=42, val_fraction=0.34) — see domain/split.py's
# pure SHA256 bucketing; verified by direct computation, not guessed.
_TRAIN_ID = "task-0"
_VAL_ID = "task-2"


class _FakeHarvester:
    def harvest(self, since: float | None = None) -> tuple[SessionDigest, ...]:
        return (SessionDigest("s1", "p", "/tmp", "intent", 0, "/tmp/t.jsonl"),)


class _FakeMiner:
    def mine(self, digests: object) -> tuple[RealTask, ...]:
        return (
            RealTask(_TRAIN_ID, "intent", "p", (), Split.TRAIN),
            RealTask(_VAL_ID, "intent", "p", (), Split.TRAIN),
        )


@dataclass
class _FakeTarget:
    """Returns a canned RolloutResult per task id, simulating what
    ClaudeCliWorker.run() now hands back after the D1 fix — including a
    timed_out=True result that Cycle must never see as a raised exception."""

    results: dict[str, RolloutResult]
    calls: list[str] = field(default_factory=list)

    def run(self, task: Task, context: str) -> RolloutResult:
        self.calls.append(task.id)
        return self.results[task.id]


class _FakeOptimizer:
    def reflect(self, state_text: str, results: object) -> list[Edit]:
        return [Edit(EditOp.ADD, Surface.MEMORY, "a rule")]


class _FakeTextState:
    name = "MEMORY.md"
    surface = Surface.MEMORY

    def read(self) -> str:
        return "baseline"

    def render(self, edits: object) -> str:
        return "candidate"


def _cycle(target: _FakeTarget, home: Path) -> Cycle:
    return Cycle(
        harvester=_FakeHarvester(),
        miner=_FakeMiner(),
        target=target,
        optimizer=_FakeOptimizer(),
        state=_FakeTextState(),
        store=FileProposalStore(home, SystemClock()),
        clock=SystemClock(),
        lock=ReflectionLock(home / "reflecting.lock"),
    )


def _config(tmp_path: Path) -> CycleConfig:
    return CycleConfig(
        target_path=tmp_path / "MEMORY.md",
        split=SplitConfig(seed=42),
        policy=GatePolicy(min_net=1, regression_budget=0),
    )


def test_timed_out_rollout_does_not_abort_run_and_is_reported(tmp_path: Path) -> None:
    target = _FakeTarget(
        results={
            _TRAIN_ID: RolloutResult(_TRAIN_ID, Score(0.0), transcript="<timeout>", timed_out=True),
            _VAL_ID: RolloutResult(_VAL_ID, Score(1.0)),
        }
    )
    report = _cycle(target, tmp_path).run(_config(tmp_path), stage=False)
    # Net effect is 0 (single val pair, baseline == candidate) so the gate
    # rejects — the point being tested is that we REACH a decision at all.
    assert report.decision == "rejected"
    assert report.timed_out_rollouts == 1


def test_no_timeouts_reports_zero(tmp_path: Path) -> None:
    target = _FakeTarget(
        results={
            _TRAIN_ID: RolloutResult(_TRAIN_ID, Score(1.0)),
            _VAL_ID: RolloutResult(_VAL_ID, Score(1.0)),
        }
    )
    report = _cycle(target, tmp_path).run(_config(tmp_path), stage=False)
    assert report.timed_out_rollouts == 0
