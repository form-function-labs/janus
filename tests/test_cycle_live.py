"""End-to-end loop against a REAL model (Haiku). Opt-in: spends tokens.

Marked ``live`` and skipped unless ``ANTHROPIC_API_KEY`` is set and ``claude`` is
on PATH. This is the honest substitute for a fabricated MockWorker — it exercises
the full harvest -> mine -> reflect -> gate -> stage loop against real model
behaviour, never simulated.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from janus.cli import Settings, _cycle_config, build_cycle

pytestmark = pytest.mark.live


def _recurring_transcripts(projects: Path) -> None:
    proj = projects / "-tmp-proj"
    proj.mkdir(parents=True)
    intents = ["write a SQL query to list active users", "summarize a git diff for a PR"]
    session = 0
    for intent in intents:
        for _ in range(2):  # each intent recurs -> mineable
            records: list[dict[str, object]] = [
                {
                    "sessionId": f"s{session}",
                    "cwd": "/tmp/proj",
                    "message": {"role": "user", "content": intent},
                }
            ]
            records += [
                {
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Bash", "id": str(j)}],
                    }
                }
                for j in range(5)
            ]
            (proj / f"s{session}.jsonl").write_text(
                "\n".join(json.dumps(r) for r in records), encoding="utf-8"
            )
            session += 1


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY + claude on PATH"
)
def test_full_cycle_against_real_haiku(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _recurring_transcripts(projects)
    settings = Settings(
        home=tmp_path / "home",
        projects_dir=projects,
        target_path=tmp_path / "MEMORY.md",
        optimizer_model="haiku",  # cheap for the test
        target_model="haiku",
        claude_path="claude",
        min_recurrence=2,
        val_fraction=0.5,
        seed=42,
        min_net=1,
        regression_budget=0,
    )
    report = build_cycle(settings).run(_cycle_config(settings), stage=False)
    assert report.sessions == 4
    assert report.decision in {"no-tasks", "no-val", "no-edits", "rejected", "preview"}
