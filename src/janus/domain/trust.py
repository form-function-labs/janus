"""Trust records — provenance, a trust score, and a falsifiable probe per lesson.

Every learned edit is *born* with provenance and a trust score; only records at
or above the inject threshold and still ``ACTIVE`` ever reach the system prompt.
A record carries a yes/no probe that periodic replay re-checks; a drifted lesson
loses trust and is quarantined (held out of context — never deleted). All
transitions are pure: they return a new record.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

TRUST_FLOOR = 0
TRUST_CEIL = 100
INJECT_THRESHOLD = 50  # below this (or quarantined), a record is held from context
PROBE_FAIL_PENALTY = 25
WEB_TRUST_PENALTY = 20


class Trigger(StrEnum):
    """What kind of evidence produced a lesson — drives its base trust."""

    CORRECTION = "correction"  # the user corrected the agent: high trust
    TECHNIQUE = "technique"  # a non-trivial technique that worked: medium
    WEB_RESEARCH = "web-research"  # sourced from the web: low (poisoning surface)


class TrustStatus(StrEnum):
    ACTIVE = "active"
    QUARANTINED = "quarantined"


_BASE_TRUST: dict[Trigger, int] = {
    Trigger.CORRECTION: 85,
    Trigger.TECHNIQUE: 65,
    Trigger.WEB_RESEARCH: 45,
}


def _clamp(value: int) -> int:
    return max(TRUST_FLOOR, min(TRUST_CEIL, value))


def base_trust(trigger: Trigger, *, web_influence: bool = False) -> int:
    return _clamp(_BASE_TRUST[trigger] - (WEB_TRUST_PENALTY if web_influence else 0))


@dataclass(frozen=True, slots=True)
class Provenance:
    session_id: str
    trigger: Trigger
    created: str  # ISO-8601, stamped by the caller (domain stays clock-free)
    web_influence: bool = False


@dataclass(frozen=True, slots=True)
class Probe:
    """A falsifiable check: does this lesson still hold?"""

    question: str
    expected: bool  # the answer that means "still holds"
    history: tuple[bool, ...] = ()

    @property
    def pass_rate(self) -> float:
        return sum(self.history) / len(self.history) if self.history else 1.0


@dataclass(frozen=True, slots=True)
class TrustRecord:
    id: str
    text: str
    provenance: Provenance
    trust: int
    status: TrustStatus = TrustStatus.ACTIVE
    probe: Probe | None = None

    @property
    def injectable(self) -> bool:
        """Only active, sufficiently-trusted records ever enter the system prompt."""
        return self.status is TrustStatus.ACTIVE and self.trust >= INJECT_THRESHOLD

    def adjust(self, delta: int) -> TrustRecord:
        return replace(self, trust=_clamp(self.trust + delta))

    def quarantine(self) -> TrustRecord:
        return replace(self, status=TrustStatus.QUARANTINED)

    def release(self) -> TrustRecord:
        """Human vouch: restore to active, trust floored just above the threshold."""
        return replace(self, status=TrustStatus.ACTIVE, trust=max(self.trust, INJECT_THRESHOLD + 5))

    def record_probe(self, passed: bool) -> TrustRecord:
        """Append a probe result; a failure costs trust and may auto-quarantine."""
        if self.probe is None:
            return self
        updated = replace(self, probe=replace(self.probe, history=(*self.probe.history, passed)))
        if passed:
            return updated
        updated = updated.adjust(-PROBE_FAIL_PENALTY)
        if updated.trust < INJECT_THRESHOLD:
            updated = updated.quarantine()
        return updated
