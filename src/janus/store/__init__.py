"""Filesystem adapters: the text-state, proposal staging, and atomic adoption."""

from __future__ import annotations

from .adopter import FileAdopter
from .memory_state import BlockTextState, ClaudeMdTextState, MemoryTextState, SkillTextState
from .proposal_store import FileProposalStore

__all__ = [
    "BlockTextState",
    "ClaudeMdTextState",
    "FileAdopter",
    "FileProposalStore",
    "MemoryTextState",
    "SkillTextState",
]
