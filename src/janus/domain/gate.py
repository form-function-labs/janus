"""The validation gate — ``limen``, the threshold an edit must cross to be kept.

Label-free by design. Instead of scoring against a gold answer (which a local
dev machine never has), we score each candidate edit by its NET EFFECT on the
user's own recurring tasks: the SkillGen *repairs minus regressions* measure,
computed on identical inputs with and without the edit. An edit is kept only if
it strictly helps **and breaks nothing** (do-no-harm).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .types import PairedOutcome


class GateDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class NetEffect:
    """The measured effect of an edit over a set of paired rollouts."""

    repairs: int  # baseline failed, candidate passed
    regressions: int  # baseline passed, candidate failed (the silent killer)
    mean_delta: float  # mean(candidate - baseline) across all pairs
    n: int

    @property
    def net(self) -> int:
        return self.repairs - self.regressions


def net_effect(pairs: Sequence[PairedOutcome]) -> NetEffect:
    """Reduce paired rollouts to repairs, regressions, and mean delta. Pure."""
    repairs = regressions = 0
    total = 0.0
    for p in pairs:
        baseline_passed = p.baseline.passed
        candidate_passed = p.candidate.passed
        if not baseline_passed and candidate_passed:
            repairs += 1
        elif baseline_passed and not candidate_passed:
            regressions += 1
        total += p.candidate.value - p.baseline.value
    n = len(pairs)
    return NetEffect(repairs, regressions, total / n if n else 0.0, n)


@dataclass(frozen=True, slots=True)
class GatePolicy:
    """How strict the gate is."""

    min_net: int = 1  # require at least this many net repairs
    regression_budget: int = 0  # do-no-harm: max tolerated hard regressions
    epsilon: float = 1e-9  # float-dust guard on the aggregate-delta check

    def __post_init__(self) -> None:
        if self.min_net < 1:
            raise ValueError("min_net must be >= 1 (a gate that accepts net 0 is not a gate)")
        if self.regression_budget < 0:
            raise ValueError("regression_budget must be >= 0")


@dataclass(frozen=True, slots=True)
class GateOutcome:
    decision: GateDecision
    effect: NetEffect
    policy: GatePolicy

    @property
    def accepted(self) -> bool:
        return self.decision is GateDecision.ACCEPT


def evaluate(effect: NetEffect, policy: GatePolicy | None = None) -> GateOutcome:
    """Apply the gate to a measured net effect. Pure."""
    pol = policy or GatePolicy()
    do_no_harm = effect.regressions <= pol.regression_budget
    improves = effect.net >= pol.min_net and effect.mean_delta > pol.epsilon
    decision = GateDecision.ACCEPT if (do_no_harm and improves) else GateDecision.REJECT
    return GateOutcome(decision, effect, pol)


def gate(pairs: Sequence[PairedOutcome], policy: GatePolicy | None = None) -> GateOutcome:
    """Convenience: compute the net effect from paired rollouts, then evaluate."""
    return evaluate(net_effect(pairs), policy)
