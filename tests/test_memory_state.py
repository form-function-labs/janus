from __future__ import annotations

from pathlib import Path

from janus.domain.types import Edit, EditOp, Surface
from janus.store.memory_state import (
    END,
    START,
    ClaudeMdTextState,
    MemoryTextState,
    SkillTextState,
)


def _edit(op: EditOp, target: str, replacement: str | None = None) -> Edit:
    return Edit(op, Surface.MEMORY, target, replacement)


def test_add_lands_in_protected_block_and_preserves_human_content(tmp_path: Path) -> None:
    path = tmp_path / "MEMORY.md"
    path.write_text("# My notes\n\nhand written stuff\n", encoding="utf-8")
    out = MemoryTextState(path).render([_edit(EditOp.ADD, "always add LIMIT")])
    assert "hand written stuff" in out
    assert START in out and END in out
    assert "- always add LIMIT" in out


def test_dedup_is_case_insensitive(tmp_path: Path) -> None:
    path = tmp_path / "MEMORY.md"
    path.write_text("", encoding="utf-8")
    state = MemoryTextState(path)
    path.write_text(state.render([_edit(EditOp.ADD, "rule one")]), encoding="utf-8")
    out = state.render([_edit(EditOp.ADD, "Rule One")])
    bullets = [ln for ln in out.splitlines() if ln.strip().startswith("- ")]
    assert len(bullets) == 1


def test_replace_then_delete(tmp_path: Path) -> None:
    path = tmp_path / "MEMORY.md"
    path.write_text("", encoding="utf-8")
    state = MemoryTextState(path)
    path.write_text(state.render([_edit(EditOp.ADD, "old rule")]), encoding="utf-8")
    replaced = state.render([_edit(EditOp.REPLACE, "old rule", "new rule")])
    assert "new rule" in replaced and "old rule" not in replaced
    path.write_text(replaced, encoding="utf-8")
    assert "new rule" not in state.render([_edit(EditOp.DELETE, "new rule")])


def test_content_surrounding_an_existing_block_survives(tmp_path: Path) -> None:
    path = tmp_path / "MEMORY.md"
    path.write_text(f"top matter\n\n{START}\n- old\n{END}\n\nbottom matter\n", encoding="utf-8")
    out = MemoryTextState(path).render([_edit(EditOp.ADD, "fresh")])
    assert "top matter" in out
    assert "bottom matter" in out
    assert "- fresh" in out


def test_skill_state_applies_only_matching_surface_edits(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text("", encoding="utf-8")
    state = SkillTextState(path)
    assert state.surface is Surface.SKILL
    out = state.render(
        [
            Edit(EditOp.ADD, Surface.SKILL, "skill rule"),
            Edit(EditOp.ADD, Surface.MEMORY, "memory rule"),  # wrong surface, ignored
        ]
    )
    assert "- skill rule" in out
    assert "memory rule" not in out


def test_claude_md_state_surface(tmp_path: Path) -> None:
    state = ClaudeMdTextState(tmp_path / "CLAUDE.md")
    assert state.surface is Surface.CLAUDE_MD
    out = state.render([Edit(EditOp.ADD, Surface.CLAUDE_MD, "project rule")])
    assert "- project rule" in out
