"""A proposal — a staged, gated bundle of edits awaiting human adoption — and
the result of adopting one. Nothing here touches the filesystem; the
``ProposalStore`` and ``Adopter`` adapters do the I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gate import GateOutcome
from .types import Edit, Surface


@dataclass(frozen=True, slots=True)
class Proposal:
    """A gate-approved candidate change, ready to stage for human review."""

    surface: Surface
    target_name: str  # display name of the file the edits target (e.g. "MEMORY.md")
    target_path: str  # absolute path to that file, so adoption is self-contained
    baseline_text: str  # the live text before edits
    candidate_text: str  # the full text after applying the accepted edits
    edits: tuple[Edit, ...]
    outcome: GateOutcome  # why it passed (repairs / regressions / net)
    created: str  # ISO-8601, stamped by the caller
    staging_dir: str = ""  # filled in by the ProposalStore on stage()


@dataclass(frozen=True, slots=True)
class AdoptResult:
    adopted: bool
    target_path: str
    backup_path: str | None = None
    message: str = ""
