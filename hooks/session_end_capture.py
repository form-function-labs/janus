#!/usr/bin/env python3
"""Janus SessionEnd capture — the cheap half of the loop.

Fires on every SessionEnd. No model call: it parses the finished transcript,
decides whether the session did enough real work to be worth reviewing later,
queues a pointer, and **durably archives the transcript** (gzipped) so Janus's
corpus survives Claude Code's transcript pruning. The expensive reflection
happens later in ``janus run``.

Stdlib-only and defensive by construction: it must never raise into the
session-teardown path, so the whole body is guarded and it always exits 0.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path


def _count_tool_calls(transcript: Path) -> int:
    """Count assistant ``tool_use`` blocks by streaming the JSONL (never full-load)."""
    n = 0
    try:
        with transcript.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            n += 1
    except OSError:
        return 0
    return n


def _archive(transcript: Path, home: Path, cwd: str) -> None:
    """Durably gzip-copy the transcript so the corpus survives pruning. Idempotent."""
    try:
        encoded = cwd.replace("/", "-") or "unknown"
        dest_dir = home / "archive" / encoded
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (transcript.stem + ".jsonl.gz")
        if dest.exists():
            return
        tmp = dest.parent / (dest.name + ".tmp")
        with transcript.open("rb") as src, gzip.open(tmp, "wb") as out:
            shutil.copyfileobj(src, out)
        os.replace(tmp, dest)  # atomic
    except OSError:
        return


def main() -> int:
    # Anti-recursion: never capture a session spawned by Janus's own worker.
    if os.environ.get("JANUS_REVIEWING"):
        return 0

    home = Path(os.environ.get("JANUS_HOME", str(Path.home() / ".janus")))
    if (home / "OFF").exists():  # kill switch
        return 0

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0

    raw_path = data.get("transcript_path")
    if not raw_path:
        return 0
    transcript = Path(os.path.expanduser(raw_path))
    if not transcript.is_file():
        return 0

    try:
        min_calls = int(os.environ.get("JANUS_MIN_TOOL_CALLS", "5") or "5")
    except ValueError:
        min_calls = 5

    calls = _count_tool_calls(transcript)
    if calls < min_calls:
        return 0

    home.mkdir(parents=True, exist_ok=True)
    _archive(transcript, home, str(data.get("cwd") or ""))

    inbox = home / "inbox.jsonl"
    key = str(transcript)
    if inbox.exists():
        try:
            with inbox.open(encoding="utf-8") as fh:
                if any(key in line for line in fh):
                    return 0
        except OSError:
            pass

    record = {
        "transcript_path": key,
        "cwd": data.get("cwd"),
        "session_id": data.get("session_id"),
        "reason": data.get("reason"),
        "tool_calls": calls,
        "queued_at": datetime.now(UTC).isoformat(),
    }
    try:
        with inbox.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        return 0
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # never break session teardown
        raise SystemExit(0) from None
