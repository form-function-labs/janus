---
description: "Janus — review past sessions and propose gated memory/skill improvements (dry-run | run | status | adopt | harvest)."
argument-hint: "[dry-run|run|status|adopt|harvest]"
allowed-tools: Bash(uv run:*)
---

Run the Janus engine with the user's requested action, then report.

The action is `$ARGUMENTS` (default to `status` if empty). Run:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" janus ${ARGUMENTS:-status}
```

Then:

- Summarize what Janus reported (sessions mined, candidate edits, gate decisions).
- For `run`: a proposal is **staged**, nothing live changed — remind the user to review it and run `/janus adopt` to apply (it backs up first and is reversible).
- For `dry-run`: nothing was staged; it's a safe preview.
- For `adopt`: confirm which file(s) changed and where the backup was written.

Never edit memory, skills, or `CLAUDE.md` yourself — Janus owns that path through its
gate. Your job is only to invoke it and relay the result.
