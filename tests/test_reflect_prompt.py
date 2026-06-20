"""Deterministic tests for the optimizer's prompt assembly and edit parsing.

These lock down the contract that prevents the 'edits target evidence text'
regression: the DOCUMENT and EVIDENCE must be unambiguously fenced, evidence must
never be formatted as an editable ``- `` bullet, and the parser must collapse a
multi-line ``add`` into a single clean rule. No model is involved — we test the
assembly, not behaviour.
"""

from __future__ import annotations

from janus.domain.types import EditOp, RolloutResult, Score, Surface
from janus.worker.claude_cli import _parse_edits, _reflect_prompt


def _fail(transcript: str, lesson: str = "", rubric: str = "") -> RolloutResult:
    return RolloutResult("f", Score(0.1), False, transcript, lesson=lesson, rubric=rubric)


def _ok(transcript: str) -> RolloutResult:
    return RolloutResult("s", Score(0.9), True, transcript)


def test_prompt_fences_document_and_evidence() -> None:
    prompt = _reflect_prompt("DOC_BODY", [_fail("boom")], [_ok("good")], Surface.MEMORY)
    # The editable region and the read-only region are explicitly fenced.
    assert "=== DOCUMENT" in prompt
    assert "=== END DOCUMENT ===" in prompt
    assert "=== EVIDENCE" in prompt
    assert "READ-ONLY" in prompt
    # The document body sits inside the DOCUMENT fence, before the EVIDENCE fence.
    assert prompt.index("DOC_BODY") < prompt.index("=== EVIDENCE")


def test_evidence_is_not_formatted_as_editable_bullets() -> None:
    """The root cause: evidence rendered as ``- FAILED:`` bullets was mistaken for
    document bullets. Evidence rows must never start with a markdown ``- ``."""
    prompt = _reflect_prompt(
        "doc", [_fail("a failing rollout body")], [_ok("a passing body")], Surface.MEMORY
    )
    evidence = prompt.split("=== EVIDENCE", 1)[1].split("=== END EVIDENCE", 1)[0]
    for line in evidence.splitlines():
        assert not line.lstrip().startswith("- "), f"evidence line looks editable: {line!r}"


def test_distilled_lessons_are_surfaced_to_the_optimizer() -> None:
    prompt = _reflect_prompt(
        "doc",
        [_fail("gh pr create ...", lesson="Use Graphite (gt) for PRs, not the gh CLI")],
        [],
        Surface.MEMORY,
    )
    assert "[LESSON] Use Graphite (gt) for PRs, not the gh CLI" in prompt


def test_lessons_dedup_case_insensitively() -> None:
    prompt = _reflect_prompt(
        "doc",
        [_fail("x", lesson="Review diffs"), _fail("y", lesson="review diffs")],
        [],
        Surface.MEMORY,
    )
    assert prompt.count("[LESSON]") == 1


def test_prompt_without_lessons_falls_back_to_rollouts() -> None:
    prompt = _reflect_prompt("doc", [_fail("only a transcript")], [], Surface.MEMORY)
    assert "infer rules from the failing rollouts" in prompt
    assert "[FAILED-ROLLOUT] only a transcript" in prompt


def test_parse_collapses_multiline_add_into_one_rule() -> None:
    """An ``add`` that crams several newline-joined sub-bullets must become ONE
    clean bullet — the second observed garbage mode."""
    raw = (
        '[{"op": "add", "target": "Rule one\\n- Rule two\\n- Rule three", '
        '"replacement": null, "rationale": "x"}]'
    )
    edits = _parse_edits(raw, Surface.MEMORY)
    assert len(edits) == 1
    assert edits[0].target == "Rule one"
    assert "\n" not in edits[0].target


def test_parse_strips_leading_bullet_marker_on_add() -> None:
    raw = '[{"op": "add", "target": "- Already a bullet", "replacement": null}]'
    edits = _parse_edits(raw, Surface.MEMORY)
    assert edits[0].target == "Already a bullet"


def test_parse_keeps_delete_target_verbatim_for_matching() -> None:
    """DELETE/REPLACE targets must stay verbatim so they can match an existing
    bullet; only ADD targets are collapsed."""
    raw = '[{"op": "delete", "target": "Prefer ripgrep over grep"}]'
    edits = _parse_edits(raw, Surface.MEMORY)
    assert edits[0].op is EditOp.DELETE
    assert edits[0].target == "Prefer ripgrep over grep"
