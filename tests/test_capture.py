"""Tests for the cheap SessionEnd capture hook (run as a real subprocess)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CAPTURE = Path(__file__).resolve().parents[1] / "hooks" / "session_end_capture.py"


def _transcript(path: Path, tool_calls: int) -> None:
    lines = [
        json.dumps({"sessionId": "s", "cwd": "/a/b", "message": {"role": "user", "content": "hi"}})
    ]
    for i in range(tool_calls):
        lines.append(
            json.dumps(
                {
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Bash", "id": str(i)}],
                    }
                }
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _run(
    transcript: Path, home: Path, *, reviewing: bool = False
) -> subprocess.CompletedProcess[str]:
    payload = json.dumps(
        {"transcript_path": str(transcript), "cwd": "/a/b", "session_id": "s", "reason": "clear"}
    )
    env = dict(os.environ, JANUS_HOME=str(home))
    if reviewing:
        env["JANUS_REVIEWING"] = "1"
    else:
        env.pop("JANUS_REVIEWING", None)
    return subprocess.run(
        [sys.executable, str(CAPTURE)], input=payload, text=True, capture_output=True, env=env
    )


def test_capture_queues_when_above_threshold(tmp_path: Path) -> None:
    transcript = tmp_path / "s.jsonl"
    _transcript(transcript, 6)
    home = tmp_path / "home"
    result = _run(transcript, home)
    assert result.returncode == 0
    inbox = home / "inbox.jsonl"
    assert inbox.exists()
    record = json.loads(inbox.read_text(encoding="utf-8").strip())
    assert record["tool_calls"] == 6
    assert record["transcript_path"] == str(transcript)


def test_capture_skips_below_threshold(tmp_path: Path) -> None:
    transcript = tmp_path / "s.jsonl"
    _transcript(transcript, 2)
    home = tmp_path / "home"
    _run(transcript, home)
    assert not (home / "inbox.jsonl").exists()


def test_capture_respects_reviewing_guard(tmp_path: Path) -> None:
    transcript = tmp_path / "s.jsonl"
    _transcript(transcript, 9)
    home = tmp_path / "home"
    _run(transcript, home, reviewing=True)
    assert not (home / "inbox.jsonl").exists()
