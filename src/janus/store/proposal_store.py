"""Proposal staging — writes a reviewable proposal to disk and reads the latest back.

Nothing live changes here; this is the holding area between ``run`` (stages) and
``adopt`` (applies). Each staging dir carries the candidate text, the full
proposal record, and a ``backup/`` slot the adopter uses.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from ..domain.gate import GateDecision, GateOutcome, GatePolicy, NetEffect
from ..domain.proposal import Proposal
from ..domain.types import Edit, EditOp, Surface
from ..ports import Clock


def _edit_to_dict(edit: Edit) -> dict[str, object]:
    return {
        "op": edit.op.value,
        "surface": edit.surface.value,
        "target": edit.target,
        "replacement": edit.replacement,
        "rationale": edit.rationale,
    }


def _edit_from_dict(data: Mapping[str, object]) -> Edit:
    replacement = data.get("replacement")
    return Edit(
        EditOp(str(data["op"])),
        Surface(str(data["surface"])),
        str(data["target"]),
        replacement if isinstance(replacement, str) else None,
        str(data.get("rationale", "")),
    )


def _outcome_to_dict(outcome: GateOutcome) -> dict[str, object]:
    return {
        "decision": outcome.decision.value,
        "repairs": outcome.effect.repairs,
        "regressions": outcome.effect.regressions,
        "mean_delta": outcome.effect.mean_delta,
        "n": outcome.effect.n,
        "policy": {
            "min_net": outcome.policy.min_net,
            "regression_budget": outcome.policy.regression_budget,
            "epsilon": outcome.policy.epsilon,
        },
    }


def _as_int(value: object) -> int:
    assert isinstance(value, (int, float))
    return int(value)


def _as_float(value: object) -> float:
    assert isinstance(value, (int, float))
    return float(value)


def _outcome_from_dict(data: Mapping[str, object]) -> GateOutcome:
    effect = NetEffect(
        _as_int(data["repairs"]),
        _as_int(data["regressions"]),
        _as_float(data["mean_delta"]),
        _as_int(data["n"]),
    )
    pol = data["policy"]
    assert isinstance(pol, Mapping)
    policy = GatePolicy(
        _as_int(pol["min_net"]),
        _as_int(pol["regression_budget"]),
        _as_float(pol["epsilon"]),
    )
    return GateOutcome(GateDecision(str(data["decision"])), effect, policy)


def _to_dict(proposal: Proposal) -> dict[str, object]:
    return {
        "surface": proposal.surface.value,
        "target_name": proposal.target_name,
        "target_path": proposal.target_path,
        "baseline_text": proposal.baseline_text,
        "candidate_text": proposal.candidate_text,
        "edits": [_edit_to_dict(e) for e in proposal.edits],
        "outcome": _outcome_to_dict(proposal.outcome),
        "created": proposal.created,
        "staging_dir": proposal.staging_dir,
    }


def _from_dict(data: Mapping[str, object]) -> Proposal:
    edits = data["edits"]
    assert isinstance(edits, list)
    outcome = data["outcome"]
    assert isinstance(outcome, Mapping)
    return Proposal(
        surface=Surface(str(data["surface"])),
        target_name=str(data["target_name"]),
        target_path=str(data.get("target_path", "")),
        baseline_text=str(data.get("baseline_text", "")),
        candidate_text=str(data["candidate_text"]),
        edits=tuple(_edit_from_dict(e) for e in edits),
        outcome=_outcome_from_dict(outcome),
        created=str(data["created"]),
        staging_dir=str(data.get("staging_dir", "")),
    )


class FileProposalStore:
    def __init__(self, home: Path, clock: Clock) -> None:
        self._staging = home / "staging"
        self._clock = clock

    def stage(self, proposal: Proposal) -> str:
        stamp = self._clock.now_iso().replace(":", "").replace("-", "").replace(".", "")
        target_dir = self._staging / stamp
        (target_dir / "backup").mkdir(parents=True, exist_ok=True)
        staged = replace(proposal, staging_dir=str(target_dir))
        (target_dir / "proposal.json").write_text(
            json.dumps(_to_dict(staged), indent=2), encoding="utf-8"
        )
        (target_dir / "proposed.md").write_text(staged.candidate_text, encoding="utf-8")
        return str(target_dir)

    def latest(self) -> Proposal | None:
        if not self._staging.is_dir():
            return None
        dirs = sorted(p for p in self._staging.iterdir() if p.is_dir())
        if not dirs:
            return None
        record = dirs[-1] / "proposal.json"
        if not record.is_file():
            return None
        return _from_dict(json.loads(record.read_text(encoding="utf-8")))
