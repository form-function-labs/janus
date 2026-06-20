from __future__ import annotations

from pathlib import Path

from janus.clock import SystemClock
from janus.domain.gate import gate
from janus.domain.proposal import Proposal
from janus.domain.types import Edit, EditOp, PairedOutcome, Score, Surface
from janus.store.adopter import FileAdopter
from janus.store.proposal_store import FileProposalStore


def _proposal(target: Path, candidate: str = "new content") -> Proposal:
    outcome = gate([PairedOutcome("t", Score(0.0), Score(1.0))])
    return Proposal(
        surface=Surface.MEMORY,
        target_name=target.name,
        target_path=str(target),
        baseline_text="old content",
        candidate_text=candidate,
        edits=(Edit(EditOp.ADD, Surface.MEMORY, "a rule"),),
        outcome=outcome,
        created="2026-06-19T00:00:00Z",
    )


def test_stage_and_latest_roundtrip(tmp_path: Path) -> None:
    store = FileProposalStore(tmp_path, SystemClock())
    target = tmp_path / "MEMORY.md"
    staged_dir = store.stage(_proposal(target))
    assert Path(staged_dir).is_dir()

    latest = store.latest()
    assert latest is not None
    assert latest.target_path == str(target)
    assert latest.candidate_text == "new content"
    assert latest.outcome.effect.net == 1
    assert latest.edits[0].op is EditOp.ADD


def test_adopt_is_atomic_with_backup(tmp_path: Path) -> None:
    store = FileProposalStore(tmp_path, SystemClock())
    target = tmp_path / "MEMORY.md"
    target.write_text("old content", encoding="utf-8")
    store.stage(_proposal(target, "new content"))

    latest = store.latest()
    assert latest is not None
    result = FileAdopter().adopt(latest)
    assert result.adopted
    assert target.read_text() == "new content"
    assert result.backup_path is not None
    assert Path(result.backup_path).read_text() == "old content"


def test_rollback_restores_prior_content(tmp_path: Path) -> None:
    store = FileProposalStore(tmp_path, SystemClock())
    target = tmp_path / "MEMORY.md"
    target.write_text("old", encoding="utf-8")
    store.stage(_proposal(target, "new"))

    latest = store.latest()
    assert latest is not None
    adopter = FileAdopter()
    result = adopter.adopt(latest)
    assert target.read_text() == "new"
    assert adopter.rollback(result)
    assert target.read_text() == "old"
