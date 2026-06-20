"""The orchestrator — one 'night' of Janus.

Wires the ports into the loop:

    harvest -> mine -> split -> reflect (optimizer) -> render candidate
            -> gate on held-out tasks (paired, with/without the edit)
            -> stage proposal

It speaks only to ports, never to a concrete adapter, and it runs inside the
``ReflectionLock`` so it can never recurse into itself. Nothing live is touched:
the deliverable is a *staged* proposal the user adopts separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .domain.gate import GatePolicy, gate
from .domain.proposal import Proposal
from .domain.split import SplitConfig, assign_splits
from .domain.types import Edit, PairedOutcome, Split
from .ports import (
    Clock,
    OptimizerWorker,
    ProposalStore,
    RecurrenceMiner,
    TargetWorker,
    TextState,
    TranscriptHarvester,
)
from .recursion import ReflectionLock


@dataclass(frozen=True, slots=True)
class CycleConfig:
    target_path: Path
    split: SplitConfig = field(default_factory=SplitConfig)
    policy: GatePolicy = field(default_factory=GatePolicy)
    since: float | None = None
    max_train: int = 8
    max_val: int = 8


@dataclass(frozen=True, slots=True)
class SleepReport:
    sessions: int
    tasks_mined: int
    train: int
    val: int
    edits_proposed: int
    decision: str  # no-tasks | no-val | no-edits | rejected | preview | staged
    net: int = 0
    repairs: int = 0
    regressions: int = 0
    staging_dir: str = ""
    message: str = ""
    edits: tuple[Edit, ...] = ()


@dataclass
class Cycle:
    harvester: TranscriptHarvester
    miner: RecurrenceMiner
    target: TargetWorker
    optimizer: OptimizerWorker
    state: TextState
    store: ProposalStore
    clock: Clock
    lock: ReflectionLock

    def run(self, config: CycleConfig, *, stage: bool = True) -> SleepReport:
        with self.lock:
            return self._run(config, stage=stage)

    def _run(self, config: CycleConfig, *, stage: bool) -> SleepReport:
        digests = self.harvester.harvest(config.since)
        mined = self.miner.mine(digests)
        real = assign_splits(mined, config.split)
        train = [t for t in real if t.split is Split.TRAIN][: config.max_train]
        val = [t for t in real if t.split is Split.VAL][: config.max_val]

        if not real:
            return SleepReport(
                len(digests), 0, 0, 0, 0, "no-tasks", message="No recurring tasks mined."
            )
        if not val:
            return SleepReport(
                len(digests),
                len(real),
                len(train),
                0,
                0,
                "no-val",
                message="No held-out tasks to gate against (need more recurring sessions).",
            )

        baseline = self.state.read()
        evidence = [self.target.run(task, baseline) for task in train]
        edits = list(self.optimizer.reflect(baseline, evidence))
        if not edits:
            return SleepReport(
                len(digests),
                len(real),
                len(train),
                len(val),
                0,
                "no-edits",
                message="Optimizer proposed no edits (nothing to repair on these tasks).",
            )

        candidate = self.state.render(edits)
        pairs: list[PairedOutcome] = []
        for task in val:
            baseline_score = self.target.run(task, baseline).score
            candidate_score = self.target.run(task, candidate).score
            pairs.append(PairedOutcome(task.id, baseline_score, candidate_score))

        outcome = gate(pairs, config.policy)
        effect = outcome.effect
        if not outcome.accepted:
            return SleepReport(
                len(digests),
                len(real),
                len(train),
                len(val),
                len(edits),
                "rejected",
                effect.net,
                effect.repairs,
                effect.regressions,
                message="Gate rejected: no net improvement on held-out tasks without regressions.",
                edits=tuple(edits),
            )

        proposal = Proposal(
            surface=self.state.surface,
            target_name=self.state.name,
            target_path=str(config.target_path),
            baseline_text=baseline,
            candidate_text=candidate,
            edits=tuple(edits),
            outcome=outcome,
            created=self.clock.now_iso(),
        )
        staging_dir = self.store.stage(proposal) if stage else ""
        return SleepReport(
            len(digests),
            len(real),
            len(train),
            len(val),
            len(edits),
            "staged" if stage else "preview",
            effect.net,
            effect.repairs,
            effect.regressions,
            staging_dir,
            "Proposal staged — review it, then run `/janus adopt`."
            if stage
            else "Dry-run preview; nothing staged.",
            edits=tuple(edits),
        )
