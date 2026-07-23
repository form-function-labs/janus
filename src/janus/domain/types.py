"""Core value objects shared across the domain.

All types are frozen + slotted: immutability is the point. A value object can't
be mutated into an invalid state, and it's hashable (free dedup for recurring
task ids). Transitions return new instances rather than mutating.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Split(StrEnum):
    """Which held-out bucket a real task lands in."""

    TRAIN = "train"
    VAL = "val"
    TEST = "test"


class EditOp(StrEnum):
    """A bounded edit to the text-state — the only operations the optimizer may propose."""

    ADD = "add"
    DELETE = "delete"
    REPLACE = "replace"


class Surface(StrEnum):
    """Which bounded markdown text-state an edit targets."""

    MEMORY = "memory"
    SKILL = "skill"
    CLAUDE_MD = "claude_md"


@dataclass(frozen=True, slots=True)
class Score:
    """A task outcome score in ``[0, 1]``."""

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"Score must be in [0, 1], got {self.value!r}")

    @property
    def passed(self) -> bool:
        """A task is considered solved at or above the pass threshold."""
        return self.value >= PASS_THRESHOLD


PASS_THRESHOLD = 0.5
"""Score at/above which a task counts as 'solved' for repairs/regressions accounting."""


# --- Tasks -------------------------------------------------------------------
# Typestate: a real task carries a split; a dream task structurally cannot.
# "A dream in the val set" is therefore unrepresentable — there is no field for it.


@dataclass(frozen=True, slots=True)
class RealTask:
    """A task mined from the user's own transcripts.

    Either a recurring intent (``rubric`` empty, judged generically) or a
    correction-derived task whose ``rubric`` is the gradeable criterion the
    output must satisfy to honour the correction.
    """

    id: str
    intent: str
    project: str
    source_sessions: tuple[str, ...]
    split: Split
    rubric: str = ""  # gradeable criterion the output must satisfy (judge sees this)
    lesson: str = ""  # distilled durable rule the optimizer should encode as a memory bullet


@dataclass(frozen=True, slots=True)
class CorrectionVerdict:
    """A classifier's judgment on a candidate correction."""

    is_correction: bool
    rubric: str = ""  # one-line testable criterion the output must satisfy
    lesson: str = ""  # one-line durable rule worth remembering


@dataclass(frozen=True, slots=True)
class DreamTask:
    """A synthetic variant of a real task — always training data, by construction.

    Note the absence of a ``split`` field. This is the invariant as a type.
    """

    id: str
    intent: str
    seed_id: str  # the RealTask this was dreamed from


Task = RealTask | DreamTask
"""Either a real (split-bearing) task or a dream (train-only) task."""


# --- Edits & rollouts --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Edit:
    """A single bounded edit the optimizer proposes against a text-state."""

    op: EditOp
    surface: Surface
    target: str  # the line/bullet to add, or the existing text to delete/replace
    replacement: str | None = None  # required for REPLACE
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.op is EditOp.REPLACE and self.replacement is None:
            raise ValueError("REPLACE edit requires a replacement")


@dataclass(frozen=True, slots=True)
class RolloutResult:
    """The outcome of replaying one task under a given text-state."""

    task_id: str
    score: Score
    tool_invoked: bool = False  # observed from the worker, not self-reported
    transcript: str = ""
    lesson: str = ""  # distilled rule from the task's correction, carried for the optimizer
    rubric: str = ""  # the gradeable criterion this rollout was judged against
    timed_out: bool = False  # worker hit its timeout — scored 0.0 but distinct from a bad answer


@dataclass(frozen=True, slots=True)
class PairedOutcome:
    """The same task scored *with* and *without* a candidate edit, on identical input.

    The paired design is what makes the gate label-free: we never need a gold
    answer, only the difference the edit makes on the user's own task.
    """

    task_id: str
    baseline: Score  # text-state WITHOUT the candidate edit
    candidate: Score  # text-state WITH the candidate edit


@dataclass(frozen=True, slots=True)
class Correction:
    """A point where the user corrected or redirected the agent.

    The richest memory signal. ``request`` is the task that led to the corrected
    behaviour; ``correction`` is what the user said to fix it — which doubles as
    a gradeable rubric ("does the output now satisfy this?"). One correction is
    worth more than ten benign recurrences.
    """

    request: str
    correction: str


@dataclass(frozen=True, slots=True)
class SessionDigest:
    """A cheap, structured summary of one finished session — no transcript body.

    This is what the harvester emits: enough to mine recurring tasks *and*
    corrections from, without re-ingesting the (possibly huge) transcript.
    """

    session_id: str
    project: str
    cwd: str
    intent: str  # the task the session was about (typically the first user ask)
    tool_calls: int
    transcript_path: str
    corrections: tuple[Correction, ...] = ()
