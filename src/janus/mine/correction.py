"""Correction miner — turns candidate corrections into gradeable tasks.

The harvester's regex is a cheap pre-filter (~30% precision); this miner asks a
classifier (Haiku) to confirm each candidate is a genuine correction and to
extract the RUBRIC — the one-line criterion the agent's output must satisfy.
Confirmed corrections become ``RealTask``s whose ``intent`` is the original
request and whose ``rubric`` is the correction-as-criterion.

Unlike recurrence, a *single* genuine correction is worth promoting — corrections
are inherently high-signal. A budget bounds classifier calls (cost control).
"""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.types import RealTask, SessionDigest, Split
from ..ports import CorrectionClassifier
from .recurrence import normalize, task_id


class CorrectionMiner:
    def __init__(self, classifier: CorrectionClassifier, max_candidates: int = 20) -> None:
        self._classifier = classifier
        self._max = max_candidates

    def mine(self, digests: Sequence[SessionDigest]) -> Sequence[RealTask]:
        tasks: list[RealTask] = []
        seen: set[str] = set()
        budget = self._max
        for digest in digests:
            for corr in digest.corrections:
                if budget <= 0:
                    return tasks
                if not corr.request.strip():
                    continue
                budget -= 1
                verdict = self._classifier.classify_correction(corr.request, corr.correction)
                if not verdict.is_correction or not verdict.rubric.strip():
                    continue
                tid = task_id(digest.project, normalize(f"{corr.request} :: {verdict.rubric}"))
                if tid in seen:
                    continue
                seen.add(tid)
                tasks.append(
                    RealTask(
                        tid,
                        corr.request,
                        digest.project,
                        (digest.session_id,),
                        Split.TRAIN,
                        rubric=verdict.rubric,
                    )
                )
        return tasks
