from __future__ import annotations

from janus.domain.types import Correction, CorrectionVerdict, RealTask, SessionDigest
from janus.mine import CompositeMiner, CorrectionMiner, HeuristicMiner


class StubClassifier:
    """In-test classifier (control-flow only, NOT a model simulator).

    Confirms a correction iff its text mentions 'JWT'. Lets us test the miner's
    promote/reject/budget/dedup logic deterministically; the real classifier is
    exercised by the live test.
    """

    def classify_correction(self, request: str, correction: str) -> CorrectionVerdict:
        if "jwt" in correction.lower():
            return CorrectionVerdict(True, rubric=f"must: {correction}", lesson="use JWT")
        return CorrectionVerdict(False)


def _digest(sid: str, corrections: tuple[Correction, ...]) -> SessionDigest:
    return SessionDigest(sid, "proj", "/p", "intent", 5, f"/{sid}.jsonl", corrections)


def test_promotes_confirmed_rejects_unconfirmed() -> None:
    digests = [
        _digest("s1", (Correction("implement auth", "no, use JWT not sessions"),)),
        _digest("s2", (Correction("write a loop", "actually that's fine, thanks"),)),
    ]
    tasks = list(CorrectionMiner(StubClassifier()).mine(digests))
    assert len(tasks) == 1
    task = tasks[0]
    assert isinstance(task, RealTask)
    assert task.intent == "implement auth"
    assert task.rubric.startswith("must:")


def test_threads_distilled_lesson_onto_task() -> None:
    """The lesson the classifier distils must survive onto the RealTask so the
    optimizer can encode it directly (regression guard for the dropped-lesson bug)."""
    digests = [_digest("s1", (Correction("implement auth", "no, use JWT not sessions"),))]
    task = next(iter(CorrectionMiner(StubClassifier()).mine(digests)))
    assert task.lesson == "use JWT"


def test_budget_caps_classifier_calls() -> None:
    many = tuple(Correction(f"req {i}", "use JWT") for i in range(10))
    tasks = list(CorrectionMiner(StubClassifier(), max_candidates=3).mine([_digest("s1", many)]))
    assert len(tasks) == 3


def test_dedups_identical_correction_tasks() -> None:
    dup = (Correction("same req", "use JWT here"), Correction("same req", "use JWT here"))
    tasks = list(CorrectionMiner(StubClassifier()).mine([_digest("s1", dup)]))
    assert len(tasks) == 1


def test_composite_combines_recurrence_and_corrections() -> None:
    d1 = SessionDigest(
        "s1", "proj", "/p", "fix bug", 5, "/s1.jsonl", (Correction("do x", "use JWT"),)
    )
    d2 = SessionDigest("s2", "proj", "/p", "fix bug", 5, "/s2.jsonl", ())
    composite = CompositeMiner(HeuristicMiner(2), CorrectionMiner(StubClassifier()))
    intents = {t.intent for t in composite.mine([d1, d2])}
    assert "fix bug" in intents  # recurrence (seen 2x)
    assert "do x" in intents  # correction (1 confirmed)
