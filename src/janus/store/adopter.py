"""Atomic adopter.

Applies a staged proposal to its live target file — but only ever via a
temp-file + ``os.replace`` (atomic on POSIX), after copying the prior file into
the staging ``backup/`` slot. The reference impl wrote straight onto the live
file with a single overwritable backup; this one is crash-safe and reversible.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..domain.proposal import AdoptResult, Proposal


class FileAdopter:
    def adopt(self, proposal: Proposal) -> AdoptResult:
        if not proposal.target_path:
            return AdoptResult(False, "", None, "proposal has no target_path")
        target = Path(proposal.target_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        backup_path: str | None = None
        if target.exists():
            backup_dir = (
                Path(proposal.staging_dir) / "backup" if proposal.staging_dir else target.parent
            )
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / target.name
            shutil.copy2(target, backup)
            backup_path = str(backup)

        tmp = target.parent / f".{target.name}.janus.tmp"
        tmp.write_text(proposal.candidate_text, encoding="utf-8")
        os.replace(tmp, target)  # atomic swap
        return AdoptResult(True, str(target), backup_path, "adopted")

    def rollback(self, result: AdoptResult) -> bool:
        """Restore a target from its backup. Returns True on success."""
        if not result.backup_path:
            return False
        backup = Path(result.backup_path)
        if not backup.is_file():
            return False
        target = Path(result.target_path)
        tmp = target.parent / f".{target.name}.janus.rollback.tmp"
        shutil.copy2(backup, tmp)
        os.replace(tmp, target)
        return True
