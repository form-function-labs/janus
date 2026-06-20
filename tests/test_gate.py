from __future__ import annotations

import pytest

from janus.domain.gate import GateDecision, GatePolicy, gate, net_effect
from janus.domain.types import PairedOutcome, Score


def _pair(baseline: float, candidate: float) -> PairedOutcome:
    return PairedOutcome("t", Score(baseline), Score(candidate))


def test_net_effect_counts_repairs_and_regressions() -> None:
    effect = net_effect([_pair(0.0, 1.0), _pair(1.0, 0.0), _pair(1.0, 1.0)])
    assert effect.repairs == 1
    assert effect.regressions == 1
    assert effect.net == 0
    assert effect.n == 3


def test_gate_accepts_clean_repair() -> None:
    outcome = gate([_pair(0.0, 1.0)])
    assert outcome.accepted
    assert outcome.decision is GateDecision.ACCEPT


def test_gate_rejects_regression_even_with_repair() -> None:
    # do-no-harm: one repair + one regression -> reject.
    assert not gate([_pair(0.0, 1.0), _pair(1.0, 0.0)]).accepted


def test_gate_rejects_net_zero() -> None:
    # no pass flips at all -> net 0 -> reject.
    assert not gate([_pair(0.4, 0.45)]).accepted


def test_regression_budget_allows_tolerated_regression() -> None:
    policy = GatePolicy(min_net=1, regression_budget=1)
    outcome = gate([_pair(0.0, 1.0), _pair(0.0, 1.0), _pair(1.0, 0.0)], policy)
    assert outcome.effect.repairs == 2
    assert outcome.effect.regressions == 1
    assert outcome.accepted


def test_epsilon_guards_aggregate_erosion() -> None:
    # one repair (net 1, no hard regression) but the document erodes another task
    # below the mean-delta floor -> conservative reject.
    outcome = gate([_pair(0.49, 0.51), _pair(0.9, 0.55)])
    assert outcome.effect.net == 1
    assert outcome.effect.regressions == 0
    assert not outcome.accepted


def test_policy_validation() -> None:
    with pytest.raises(ValueError):
        GatePolicy(min_net=0)
    with pytest.raises(ValueError):
        GatePolicy(regression_budget=-1)


def test_score_range_enforced() -> None:
    with pytest.raises(ValueError):
        Score(1.5)
