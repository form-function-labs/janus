from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from janus.harvest import JsonlTranscriptHarvester


def _write(path: Path, records: Sequence[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def test_harvest_extracts_digest(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "-Users-x-proj"
    proj.mkdir(parents=True)
    _write(
        proj / "sess1.jsonl",
        [
            {
                "sessionId": "sess1",
                "cwd": "/Users/x/proj",
                "message": {"role": "user", "content": "fix the auth bug"},
            },
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "ok"},
                        {"type": "tool_use", "name": "Edit", "id": "1"},
                    ],
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Bash", "id": "2"}],
                }
            },
        ],
    )
    digests = JsonlTranscriptHarvester(tmp_path / "projects").harvest()
    assert len(digests) == 1
    digest = digests[0]
    assert digest.session_id == "sess1"
    assert digest.project == "proj"
    assert digest.intent == "fix the auth bug"
    assert digest.tool_calls == 2


def test_harvest_handles_list_format_user_content(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "p"
    proj.mkdir(parents=True)
    _write(
        proj / "s.jsonl",
        [
            {
                "sessionId": "s",
                "cwd": "/a/b",
                "message": {"role": "user", "content": [{"type": "text", "text": "do the thing"}]},
            }
        ],
    )
    assert JsonlTranscriptHarvester(tmp_path / "projects").harvest()[0].intent == "do the thing"


def test_harvest_skips_harness_wrappers_for_intent(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "p"
    proj.mkdir(parents=True)
    _write(
        proj / "s.jsonl",
        [
            {
                "sessionId": "s",
                "cwd": "/a/b",
                "message": {"role": "user", "content": "<system-reminder>noise</system-reminder>"},
            },
            {"sessionId": "s", "message": {"role": "user", "content": "the real ask"}},
        ],
    )
    assert JsonlTranscriptHarvester(tmp_path / "projects").harvest()[0].intent == "the real ask"


def test_corrupt_lines_are_tolerated(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "p"
    proj.mkdir(parents=True)
    (proj / "s.jsonl").write_text(
        'not json\n{"sessionId":"s","cwd":"/a/b","message":{"role":"user","content":"x"}}\n{bad',
        encoding="utf-8",
    )
    digests = JsonlTranscriptHarvester(tmp_path / "projects").harvest()
    assert len(digests) == 1
    assert digests[0].intent == "x"
