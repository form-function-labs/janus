from __future__ import annotations

from janus.domain.trust import (
    INJECT_THRESHOLD,
    Probe,
    Provenance,
    Trigger,
    TrustRecord,
    TrustStatus,
    base_trust,
)


def _record(trust: int = 85, probe: Probe | None = None) -> TrustRecord:
    prov = Provenance("s1", Trigger.CORRECTION, "2026-06-19T00:00:00Z")
    return TrustRecord("m1", "always add a LIMIT", prov, trust, probe=probe)


def test_base_trust_by_trigger() -> None:
    assert base_trust(Trigger.CORRECTION) == 85
    assert base_trust(Trigger.TECHNIQUE) == 65
    assert base_trust(Trigger.WEB_RESEARCH) == 45
    assert base_trust(Trigger.CORRECTION, web_influence=True) == 65


def test_injectable_requires_threshold_and_active() -> None:
    assert _record(85).injectable
    assert not _record(40).injectable
    assert not _record(85).quarantine().injectable


def test_probe_failure_decrements_and_quarantines() -> None:
    record = _record(60, Probe("has LIMIT?", expected=True)).record_probe(False)
    assert record.trust == 35
    assert record.status is TrustStatus.QUARANTINED
    assert not record.injectable


def test_probe_pass_preserves_trust_and_logs_history() -> None:
    record = _record(60, Probe("q", expected=True)).record_probe(True)
    assert record.trust == 60
    assert record.probe is not None
    assert record.probe.history == (True,)


def test_release_restores_above_threshold() -> None:
    record = _record(20).quarantine().release()
    assert record.status is TrustStatus.ACTIVE
    assert record.trust >= INJECT_THRESHOLD


def test_immutability() -> None:
    record = _record(60)
    bumped = record.adjust(10)
    assert record.trust == 60  # original untouched
    assert bumped.trust == 70
