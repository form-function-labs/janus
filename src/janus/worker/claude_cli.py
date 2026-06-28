"""The only adapter that talks to a model: ``claude -p`` as target, optimizer, and
correction classifier.

Isolation flags mirror SkillOpt-Sleep's fix for the ambient-context leak
(``--bare`` and friends) and work on an API key — the chosen auth. **Fail loud**:
a non-zero exit raises ``WorkerError`` where the reference impl swallowed it into
an empty string and silently wasted a night. The spawned session carries
``JANUS_REVIEWING=1`` so its own hooks no-op (belt-and-suspenders with ``--bare``,
which already skips hooks).

Wire two instances — e.g. Haiku target + Sonnet optimizer — to honour the
optimizer ≠ target discipline.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Sequence

from beartype import beartype

from ..domain.types import (
    CorrectionVerdict,
    Edit,
    EditOp,
    RealTask,
    RolloutResult,
    Score,
    Surface,
    Task,
)

_ISOLATION_FLAGS: tuple[str, ...] = (
    "--bare",
    "--disable-slash-commands",
    "--disallowedTools",
    "*",
    "--exclude-dynamic-system-prompt-sections",
)

_NUMBER = re.compile(r"[-+]?\d*\.?\d+")
_FENCE = re.compile(r"```(?:json)?", re.I)
_WS = re.compile(r"\s+")  # collapse whitespace/newlines in evidence so it stays single-line


class WorkerError(RuntimeError):
    """``claude -p`` failed. Raised loudly rather than silently scoring zero."""


def probe_auth(claude_path: str) -> tuple[bool, str]:
    """Cheap real probe: ``claude -p ok --model haiku``.

    Returns ``(True, "")`` on success, ``(False, "<error detail>")`` on failure.
    Intended for the ``doctor`` preflight check only — not the main rollout path.
    Unit tests inject a replacement via the *probe_fn* parameter on
    ``_doctor_checks`` so CI never spawns a real model call.
    """
    cmd = [
        claude_path,
        "-p",
        "ok",
        "--output-format",
        "text",
        "--bare",
        "--model",
        "haiku",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, proc.stderr.strip()[:200]
    return True, ""


class ClaudeCliWorker:
    """Implements ``TargetWorker.run``, ``OptimizerWorker.reflect``, and
    ``CorrectionClassifier.classify_correction``."""

    def __init__(
        self,
        *,
        role: str,
        model: str,
        surface: Surface = Surface.MEMORY,
        claude_path: str = "claude",
        timeout: int = 120,
        judge_model: str = "",
    ) -> None:
        self.role = role
        self.surface = surface
        self._model = model
        # A separate (typically stronger) model for grading rollouts. Empty =
        # judge with the same model that executes — set it to lift eval reliability.
        self._judge_model = judge_model or model
        self._claude = claude_path
        self._timeout = timeout

    # --- target role ----------------------------------------------------
    @beartype
    def run(self, task: Task, context: str) -> RolloutResult:
        output = self._call(_run_prompt(task.intent, context))
        rubric = task.rubric if isinstance(task, RealTask) else ""
        lesson = task.lesson if isinstance(task, RealTask) else ""
        score = self._judge(task.intent, output, rubric)
        # Memory-surface tasks run text-only (tools disallowed), so no tool use.
        # Carry the correction's distilled lesson + rubric so the optimizer can
        # encode them directly instead of reverse-engineering from the transcript.
        return RolloutResult(
            task.id,
            score,
            tool_invoked=False,
            transcript=output,
            lesson=lesson,
            rubric=rubric,
        )

    def _judge(self, intent: str, output: str, rubric: str = "") -> Score:
        verdict = self._call(_judge_prompt(intent, output, rubric), model=self._judge_model)
        return Score(_parse_score(verdict))

    # --- optimizer role -------------------------------------------------
    @beartype
    def reflect(self, state_text: str, results: Sequence[RolloutResult]) -> Sequence[Edit]:
        failures = [r for r in results if not r.score.passed]
        successes = [r for r in results if r.score.passed]
        raw = self._call(_reflect_prompt(state_text, failures, successes, self.surface))
        try:
            return _parse_edits(raw, self.surface)
        except ValueError:
            # One retry with a firmer instruction — the intermittent non-JSON failure mode.
            raw = self._call(
                _reflect_prompt(state_text, failures, successes, self.surface, strict=True)
            )
            return _parse_edits(raw, self.surface)

    # --- correction classifier role -------------------------------------
    @beartype
    def classify_correction(self, request: str, correction: str) -> CorrectionVerdict:
        raw = self._call(_classify_prompt(request, correction))
        return _parse_verdict(raw)

    # --- transport ------------------------------------------------------
    def _build_cmd(self, prompt: str, model: str) -> list[str]:
        cmd = [self._claude, "-p", "--output-format", "text", *_ISOLATION_FLAGS]
        use_model = model or self._model
        if use_model:
            cmd += ["--model", use_model]
        cmd += ["--", prompt]
        return cmd

    def _call(self, prompt: str, model: str = "") -> str:
        cmd = self._build_cmd(prompt, model)
        env = dict(os.environ, JANUS_REVIEWING="1")
        with tempfile.TemporaryDirectory() as cwd:
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    cwd=cwd,
                    env=env,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise WorkerError(f"claude -p failed to run: {exc}") from exc
        if proc.returncode != 0:
            raise WorkerError(f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:300]}")
        return proc.stdout


# --- prompts ---------------------------------------------------------------


def _run_prompt(intent: str, context: str) -> str:
    ctx = context.strip()
    guidance = f"\n\nLearned guidance (apply if relevant):\n{ctx}\n" if ctx else "\n"
    return f"Complete the task as well as you can.{guidance}\nTask: {intent}\n"


def _judge_prompt(intent: str, output: str, rubric: str = "") -> str:
    criterion = f"It MUST satisfy this requirement: {rubric}\n" if rubric else ""
    return (
        "Grade how well the answer accomplishes the task.\n"
        f"Task: {intent}\n"
        f"{criterion}"
        f"Answer: {output[:2000]}\n"
        "Respond with ONLY a single number from 0.0 (fails) to 1.0 (fully satisfies)."
    )


def _classify_prompt(request: str, correction: str) -> str:
    return (
        "A user said the message below to an AI coding agent right after the agent acted. "
        "Decide whether it is a CORRECTION of the agent's behaviour (telling it it did "
        "something wrong or should do it differently) — as opposed to a new request, a "
        "question, gratitude, or a casual remark.\n"
        f"Prior request: {request[:300]}\n"
        f"User message: {correction[:300]}\n"
        'Respond with ONLY JSON: {"is_correction": true|false, '
        '"rubric": "<one-line testable criterion the output must satisfy, or empty>", '
        '"lesson": "<one-line durable rule worth remembering, or empty>"}.'
    )


_EDIT_SCHEMA = (
    "Respond with ONLY a JSON array of edits, each like "
    '{"op": "add"|"delete"|"replace", "target": "<text>", '
    '"replacement": "<text or null>", "rationale": "<why>"}.\n'
    "Rules for each op:\n"
    '- "add": "target" is a SINGLE new rule (one sentence, no leading "- ", no '
    "newlines). It will be appended as one bullet inside the LEARNED block.\n"
    '- "delete": "target" must be the EXACT text of an existing LEARNED bullet '
    "(quoted verbatim from the DOCUMENT below).\n"
    '- "replace": "target" is an existing LEARNED bullet quoted verbatim; '
    '"replacement" is its single-rule rewrite.\n'
    "At most 3 edits. Each edit operates ONLY on the LEARNED block of the "
    "DOCUMENT. NEVER use text from the EVIDENCE as a target — the evidence is "
    "read-only context, not part of the document you are editing."
)


def _evidence_line(prefix: str, text: str, limit: int) -> str:
    """One evidence row. Deliberately NOT a markdown bullet so the model cannot
    mistake it for an editable DOCUMENT bullet (the root cause of garbage edits)."""
    return f"  [{prefix}] {_WS.sub(' ', text.strip())[:limit]}"


def _reflect_prompt(
    state_text: str,
    failures: Sequence[RolloutResult],
    successes: Sequence[RolloutResult],
    surface: Surface,
    *,
    strict: bool = False,
) -> str:
    # Distilled lessons from confirmed corrections are the PRIMARY signal: encode
    # them as general rules. Fall back to transcript evidence when absent.
    lessons = []
    seen: set[str] = set()
    for r in failures:
        lesson = r.lesson.strip()
        if lesson and lesson.lower() not in seen:
            seen.add(lesson.lower())
            lessons.append(lesson)
    lesson_block = (
        "\n".join(_evidence_line("LESSON", line, 200) for line in lessons[:5])
        or "  (none — infer rules from the failing rollouts below)"
    )
    fail_block = (
        "\n".join(_evidence_line("FAILED-ROLLOUT", r.transcript, 280) for r in failures[:5])
        or "  (none)"
    )
    succ_block = (
        "\n".join(_evidence_line("PASSING-ROLLOUT", r.transcript, 160) for r in successes[:3])
        or "  (none)"
    )
    firm = "\nOutput JSON only. No prose, no code fences." if strict else ""
    return (
        f"You maintain the LEARNED block of a {surface.value} document for a coding "
        "agent. Your job: propose general, durable rules that would prevent the "
        "failures below — derived from the LESSONS — and add them to the LEARNED "
        "block.\n\n"
        "=== DOCUMENT (the ONLY text you may edit; only its LEARNED block is "
        f"editable) ===\n{state_text[:4000]}\n=== END DOCUMENT ===\n\n"
        "=== EVIDENCE (READ-ONLY — never edit, quote, or target this text) ===\n"
        f"Lessons distilled from the user's corrections (turn each into a rule):\n"
        f"{lesson_block}\n"
        f"Failing rollouts (what went wrong):\n{fail_block}\n"
        f"Passing rollouts (do not regress these):\n{succ_block}\n"
        "=== END EVIDENCE ===\n\n"
        f"{_EDIT_SCHEMA}{firm}"
    )


# --- parsing ---------------------------------------------------------------


def _parse_score(text: str) -> float:
    match = _NUMBER.search(text)
    if not match:
        return 0.0
    try:
        value = float(match.group())
    except ValueError:
        return 0.0
    return max(0.0, min(1.0, value))


def _extract_json(text: str) -> object:
    cleaned = _FENCE.sub("", text).strip()
    start = next((i for i, ch in enumerate(cleaned) if ch in "[{"), None)
    if start is None:
        raise ValueError("no JSON value found in model output")
    try:
        obj, _end = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in model output: {exc}") from exc
    return obj


def _parse_verdict(text: str) -> CorrectionVerdict:
    try:
        obj = _extract_json(text)
    except ValueError:
        return CorrectionVerdict(False)
    if not isinstance(obj, dict):
        return CorrectionVerdict(False)
    rubric = obj.get("rubric")
    lesson = obj.get("lesson")
    return CorrectionVerdict(
        bool(obj.get("is_correction")),
        rubric if isinstance(rubric, str) else "",
        lesson if isinstance(lesson, str) else "",
    )


def _one_rule(text: str) -> str:
    """Collapse a model-supplied rule to a single clean bullet line.

    Defense-in-depth at the adapter boundary: even if the model crams several
    newline-joined sub-bullets into one field, we keep only the first rule and
    strip any leading ``- `` so it lands as exactly one well-formed bullet.
    """
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    first = first.strip()
    if first.startswith("- "):
        first = first[2:].strip()
    return _WS.sub(" ", first)


def _parse_edits(text: str, surface: Surface) -> tuple[Edit, ...]:
    obj = _extract_json(text)
    if isinstance(obj, dict):
        obj = [obj]
    if not isinstance(obj, list):
        raise ValueError("edits must be a JSON array")
    edits: list[Edit] = []
    for item in obj:
        if not isinstance(item, dict):
            continue
        try:
            op = EditOp(str(item.get("op", "")).lower())
        except ValueError:
            continue
        target = item.get("target")
        if not isinstance(target, str) or not target.strip():
            continue
        replacement = item.get("replacement")
        replacement = replacement if isinstance(replacement, str) else None
        if op is EditOp.REPLACE and replacement is None:
            continue
        # ADD targets and any replacement must be a single clean rule, never a
        # multi-line dump. DELETE/REPLACE targets stay verbatim so they can match
        # an existing bullet (which is already a single normalized line).
        clean_target = _one_rule(target) if op is EditOp.ADD else target.strip()
        if not clean_target:
            continue
        clean_replacement = _one_rule(replacement) if replacement is not None else None
        rationale = item.get("rationale")
        edits.append(
            Edit(
                op,
                surface,
                clean_target,
                clean_replacement,
                rationale if isinstance(rationale, str) else "",
            )
        )
    return tuple(edits)
