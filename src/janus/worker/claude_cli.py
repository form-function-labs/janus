"""The only adapter that talks to a model: ``claude -p`` as both target and optimizer.

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

from ..domain.types import Edit, EditOp, RolloutResult, Score, Surface, Task

_ISOLATION_FLAGS: tuple[str, ...] = (
    "--bare",
    "--disable-slash-commands",
    "--disallowedTools",
    "*",
    "--exclude-dynamic-system-prompt-sections",
)

_NUMBER = re.compile(r"[-+]?\d*\.?\d+")
_FENCE = re.compile(r"```(?:json)?", re.I)


class WorkerError(RuntimeError):
    """``claude -p`` failed. Raised loudly rather than silently scoring zero."""


class ClaudeCliWorker:
    """Implements both ``TargetWorker.run`` and ``OptimizerWorker.reflect``."""

    def __init__(
        self,
        *,
        role: str,
        model: str,
        surface: Surface = Surface.MEMORY,
        claude_path: str = "claude",
        timeout: int = 120,
    ) -> None:
        self.role = role
        self.surface = surface
        self._model = model
        self._claude = claude_path
        self._timeout = timeout

    # --- target role ----------------------------------------------------
    @beartype
    def run(self, task: Task, context: str) -> RolloutResult:
        output = self._call(_run_prompt(task.intent, context))
        score = self._judge(task.intent, output)
        # Memory-surface tasks run text-only (tools disallowed), so no tool use.
        return RolloutResult(task.id, score, tool_invoked=False, transcript=output)

    def _judge(self, intent: str, output: str) -> Score:
        verdict = self._call(_judge_prompt(intent, output))
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

    # --- transport ------------------------------------------------------
    def _call(self, prompt: str) -> str:
        cmd = [self._claude, "-p", "--output-format", "text", *_ISOLATION_FLAGS]
        if self._model:
            cmd += ["--model", self._model]
        cmd += ["--", prompt]
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


def _judge_prompt(intent: str, output: str) -> str:
    return (
        "Grade how well the answer accomplishes the task.\n"
        f"Task: {intent}\n"
        f"Answer: {output[:2000]}\n"
        "Respond with ONLY a single number from 0.0 (useless) to 1.0 (fully correct)."
    )


_EDIT_SCHEMA = (
    "Respond with ONLY a JSON array of bounded edits, each like "
    '{"op": "add"|"delete"|"replace", "target": "<bullet text>", '
    '"replacement": "<text or null>", "rationale": "<why>"}. '
    "At most 3 edits. Keep them minimal."
)


def _reflect_prompt(
    state_text: str,
    failures: Sequence[RolloutResult],
    successes: Sequence[RolloutResult],
    surface: Surface,
    *,
    strict: bool = False,
) -> str:
    fail_block = "\n".join(f"- FAILED: {r.transcript[:300]}" for r in failures[:5]) or "(none)"
    succ_block = "\n".join(f"- OK: {r.transcript[:120]}" for r in successes[:3]) or "(none)"
    firm = "\nOutput JSON only. No prose, no code fences." if strict else ""
    return (
        f"You are improving a {surface.value} document for a coding agent.\n"
        f"Current document:\n---\n{state_text[:4000]}\n---\n"
        f"Recent failures:\n{fail_block}\n"
        f"Recent successes (preserve what works):\n{succ_block}\n"
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
        rationale = item.get("rationale")
        edits.append(
            Edit(
                op,
                surface,
                target.strip(),
                replacement,
                rationale if isinstance(rationale, str) else "",
            )
        )
    return tuple(edits)
