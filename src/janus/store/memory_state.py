"""Bounded markdown text-state — one implementation, three surfaces.

Edits land **only** inside a protected ``LEARNED`` block; everything the user
hand-wrote outside it is preserved verbatim. This is the guarantee that the
optimizer can never clobber human content — it only ever re-emits its own block.

``BlockTextState`` is parameterized by ``Surface`` so memory, skills, and
CLAUDE.md all ride the same gate/loop; only edits matching the state's surface
are applied.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from ..domain.types import Edit, EditOp, Surface

START = "<!-- JANUS:LEARNED START -->"
END = "<!-- JANUS:LEARNED END -->"

_WS = re.compile(r"\s+")


def _as_bullet(text: str) -> str:
    stripped = text.strip()
    return stripped if stripped.startswith("- ") else f"- {stripped}"


def _norm(bullet: str) -> str:
    return _WS.sub(" ", bullet.lower().strip())


def _extract_bullets(doc: str) -> list[str]:
    if START in doc and END in doc:
        block = doc.split(START, 1)[1].split(END, 1)[0]
        return [ln.strip() for ln in block.splitlines() if ln.strip().startswith("- ")]
    return []


def _strip_block(doc: str) -> str:
    if START in doc and END in doc:
        pre, rest = doc.split(START, 1)
        _, post = rest.split(END, 1)
        return (pre.rstrip() + "\n" + post.lstrip()).strip()
    return doc.strip()


def _apply_edits(bullets: list[str], edits: Sequence[Edit], surface: Surface) -> list[str]:
    out = list(bullets)
    for edit in edits:
        if edit.surface is not surface:
            continue
        if edit.op is EditOp.ADD:
            new = _as_bullet(edit.target)
            if _norm(new) not in {_norm(b) for b in out}:
                out.append(new)
        elif edit.op is EditOp.DELETE:
            target = _norm(_as_bullet(edit.target))
            out = [b for b in out if _norm(b) != target]
        elif edit.op is EditOp.REPLACE and edit.replacement is not None:
            target = _norm(_as_bullet(edit.target))
            out = [_as_bullet(edit.replacement) if _norm(b) == target else b for b in out]
    return out


class BlockTextState:
    """A ``TextState`` over a single markdown file, scoped to one ``Surface``."""

    def __init__(self, path: Path, surface: Surface) -> None:
        self._path = path
        self.name = path.name
        self.surface = surface

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> str:
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def render(self, edits: Sequence[Edit]) -> str:
        doc = self.read()
        bullets = _apply_edits(_extract_bullets(doc), edits, self.surface)
        block = START + "\n" + "\n".join(bullets) + "\n" + END
        outside = _strip_block(doc)
        return f"{outside}\n\n{block}\n" if outside else f"{block}\n"


class MemoryTextState(BlockTextState):
    def __init__(self, path: Path) -> None:
        super().__init__(path, Surface.MEMORY)


class SkillTextState(BlockTextState):
    def __init__(self, path: Path) -> None:
        super().__init__(path, Surface.SKILL)


class ClaudeMdTextState(BlockTextState):
    def __init__(self, path: Path) -> None:
        super().__init__(path, Surface.CLAUDE_MD)
